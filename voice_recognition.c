#define _GNU_SOURCE
#include "voice_recognition.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
#include <pthread.h>
#include <unistd.h> // For usleep

// Configuration constants
#define SAMPLE_RATE 16000
#define SILENCE_THRESHOLD 500       // Amplitude threshold for silence detection
#define SILENCE_DURATION_MS 1500    // 1.5 seconds of silence to auto-stop
#define MIN_SPEECH_DURATION_MS 500  // Minimum speech duration before allowing auto-stop
#define VOLUME_SMOOTHING_FACTOR 0.3 // For volume smoothing

// Internal handle structure
typedef struct
{
    CALLBACK_Recognition recog_callback;
    CALLBACK_Record record_callback;
    void *user_data;

    // Audio processing
    short *audio_buffer;
    int buffer_size;
    int buffer_capacity;

    // Silence detection
    int silence_samples;
    int speech_samples;
    int total_samples;
    int last_volume;
    int is_speech_detected;

    // Timing
    clock_t start_time;
    unsigned long timeout_ms;

    // State
    int is_active;
    int is_recording;

    // Threading
    pthread_mutex_t mutex;
    pthread_t timer_thread;

    // Results
    recogResult_t last_result;
} voice_handle_t;

// Global state
static int g_initialized = 0;
static char g_license[256] = {0};

// Timer thread function
void *timer_thread_func(void *arg)
{
    voice_handle_t *handle = (voice_handle_t *)arg;

    while (handle->is_active)
    {
        usleep(1000000); // Sleep for 1 second
        pthread_mutex_lock(&handle->mutex);
        if (handle->is_active)
        {
            clock_t current_time = clock();
            unsigned long elapsed_ms = ((current_time - handle->start_time) * 1000) / CLOCKS_PER_SEC;

            // Update result timer
            handle->last_result.nTimer = elapsed_ms;

            // Call timer callback for recognition
            if (handle->recog_callback)
            {
                handle->recog_callback(handle, handle->user_data, STATUS_TIMER, handle->last_result);
            }

            // Call timer callback for recording
            if (handle->record_callback && handle->is_recording)
            {
                recordData_t record_data = {0};
                record_data.nTimer = elapsed_ms;
                record_data.nVolume = handle->last_volume;
                handle->record_callback(handle, handle->user_data, STATUS_TIMER, record_data);
            }
        }
        pthread_mutex_unlock(&handle->mutex);
    }
    return NULL;
}

int InitEx_WithLicense(const char *license_key)
{
    if (!license_key)
    {
        return STATUS_ERR_TIMEOUT;
    }
    strncpy(g_license, license_key, sizeof(g_license) - 1);
    g_initialized = 1;
    printf("Voice Recognition Library initialized with license\n");
    return STATUS_SUCCESS;
}

HCLEVER recogStart(CALLBACK_Recognition callback, void *pUserData)
{
    if (!g_initialized)
    {
        return NULL;
    }

    voice_handle_t *handle = (voice_handle_t *)malloc(sizeof(voice_handle_t));
    if (!handle)
    {
        return NULL;
    }

    // Initialize handle
    memset(handle, 0, sizeof(voice_handle_t));
    handle->recog_callback = callback;
    handle->user_data = pUserData;
    handle->buffer_capacity = SAMPLE_RATE * 10; // 10 seconds buffer
    handle->audio_buffer = (short *)malloc(handle->buffer_capacity * sizeof(short));
    handle->timeout_ms = 30000; // 30 seconds default timeout
    handle->is_active = 1;
    handle->start_time = clock();

    pthread_mutex_init(&handle->mutex, NULL);

    // Start timer thread
    pthread_create(&handle->timer_thread, NULL, timer_thread_func, handle);

    // Call start callback
    if (callback)
    {
        callback(handle, pUserData, STATUS_START, handle->last_result);
    }

    printf("Recognition started\n");
    return (HCLEVER)handle;
}

int calculateVolume(short *samples, int numSamples)
{
    if (!samples || numSamples <= 0)
    {
        return 0;
    }

    long long sum = 0;
    for (int i = 0; i < numSamples; i++)
    {
        sum += abs(samples[i]);
    }

    int avg_amplitude = (int)(sum / numSamples);
    // Scale to 0-32767 range
    return (avg_amplitude > 32767) ? 32767 : avg_amplitude;
}

int detectSilence(short *samples, int numSamples, int threshold)
{
    if (!samples || numSamples <= 0)
    {
        return 1; // Consider empty as silence
    }

    int volume = calculateVolume(samples, numSamples);
    return volume < threshold;
}

int addSample(HCLEVER hclever, short *ipsSample, int nNumSamples)
{
    if (!hclever || !ipsSample || nNumSamples <= 0)
    {
        return STATUS_ERR_TIMEOUT;
    }

    voice_handle_t *handle = (voice_handle_t *)hclever;
    pthread_mutex_lock(&handle->mutex);

    if (!handle->is_active)
    {
        pthread_mutex_unlock(&handle->mutex);
        return STATUS_ERR_TIMEOUT;
    }

    // Expand buffer if needed
    if (handle->buffer_size + nNumSamples > handle->buffer_capacity)
    {
        handle->buffer_capacity = (handle->buffer_size + nNumSamples) * 2;
        handle->audio_buffer = (short *)realloc(handle->audio_buffer,
                                                handle->buffer_capacity * sizeof(short));
    }

    // Copy samples to buffer
    memcpy(handle->audio_buffer + handle->buffer_size, ipsSample, nNumSamples * sizeof(short));
    handle->buffer_size += nNumSamples;
    handle->total_samples += nNumSamples;

    // Calculate current volume
    int current_volume = calculateVolume(ipsSample, nNumSamples);

    // Smooth volume calculation
    if (handle->last_volume == 0)
    {
        handle->last_volume = current_volume;
    }
    else
    {
        handle->last_volume = (int)(VOLUME_SMOOTHING_FACTOR * current_volume +
                                    (1.0 - VOLUME_SMOOTHING_FACTOR) * handle->last_volume);
    }

    // Update result
    handle->last_result.nVolume = handle->last_volume;

    // Silence detection logic
    int is_silence = detectSilence(ipsSample, nNumSamples, SILENCE_THRESHOLD);

    if (is_silence)
    {
        handle->silence_samples += nNumSamples;
    }
    else
    {
        handle->speech_samples += nNumSamples;
        handle->silence_samples = 0; // Reset silence counter on speech
        handle->is_speech_detected = 1;
    }

    // Convert samples to milliseconds
    int silence_duration_ms = (handle->silence_samples * 1000) / SAMPLE_RATE;
    int speech_duration_ms = (handle->speech_samples * 1000) / SAMPLE_RATE;

    // Auto-stop logic: if we have enough speech and then silence
    if (handle->is_speech_detected &&
        speech_duration_ms >= MIN_SPEECH_DURATION_MS &&
        silence_duration_ms >= SILENCE_DURATION_MS)
    {

        // Prepare final result
        handle->last_result.nWordDura = handle->speech_samples;
        handle->last_result.nEndSil = handle->silence_samples;
        handle->last_result.nConfi = 85; // High confidence for auto-detected end
        handle->last_result.nSGDiff = 100;
        strcpy(handle->last_result.pszCmd, "AUTO_STOP_DETECTED");

        pthread_mutex_unlock(&handle->mutex);

        // Call callback with result
        if (handle->recog_callback)
        {
            handle->recog_callback(handle, handle->user_data, STATUS_RESULT, handle->last_result);
        }

        return STATUS_SUCCESS;
    }

    // Check timeout
    clock_t current_time = clock();
    unsigned long elapsed_ms = ((current_time - handle->start_time) * 1000) / CLOCKS_PER_SEC;

    if (elapsed_ms > handle->timeout_ms)
    {
        pthread_mutex_unlock(&handle->mutex);

        if (handle->recog_callback)
        {
            handle->recog_callback(handle, handle->user_data, STATUS_ERR_TIMEOUT, handle->last_result);
        }

        return STATUS_ERR_TIMEOUT;
    }

    pthread_mutex_unlock(&handle->mutex);

    // Call callback for ongoing processing
    if (handle->recog_callback)
    {
        int status = handle->is_speech_detected ? STATUS_STD : STATUS_TIMER;
        handle->recog_callback(handle, handle->user_data, status, handle->last_result);
    }

    return STATUS_ERR_NEEDMORESAMPLE;
}

int recogStop(HCLEVER hclever)
{
    if (!hclever)
    {
        return STATUS_ERR_TIMEOUT;
    }

    voice_handle_t *handle = (voice_handle_t *)hclever;

    pthread_mutex_lock(&handle->mutex);
    handle->is_active = 0;
    pthread_mutex_unlock(&handle->mutex);

    // Wait for timer thread to finish
    pthread_join(handle->timer_thread, NULL);

    // Call finish callback
    if (handle->recog_callback)
    {
        handle->recog_callback(handle, handle->user_data, STATUS_FINISH, handle->last_result);
    }

    printf("Recognition stopped\n");
    return STATUS_SUCCESS;
}

recogResult_t getResult(HCLEVER hclever)
{
    recogResult_t empty_result = {0};

    if (!hclever)
    {
        return empty_result;
    }

    voice_handle_t *handle = (voice_handle_t *)hclever;

    pthread_mutex_lock(&handle->mutex);
    recogResult_t result = handle->last_result;
    pthread_mutex_unlock(&handle->mutex);

    return result;
}

int release(HCLEVER hclever)
{
    if (!hclever)
    {
        return STATUS_ERR_TIMEOUT;
    }

    voice_handle_t *handle = (voice_handle_t *)hclever;

    // Stop if still active
    if (handle->is_active)
    {
        recogStop(hclever);
    }

    // Clean up resources
    pthread_mutex_destroy(&handle->mutex);

    if (handle->audio_buffer)
    {
        free(handle->audio_buffer);
    }

    free(handle);

    printf("Handle released\n");
    return STATUS_SUCCESS;
}

HCLEVER recordStart(CALLBACK_Record callback, void *pUserData)
{
    if (!g_initialized)
    {
        return NULL;
    }

    voice_handle_t *handle = (voice_handle_t *)malloc(sizeof(voice_handle_t));
    if (!handle)
    {
        return NULL;
    }

    // Initialize handle for recording
    memset(handle, 0, sizeof(voice_handle_t));
    handle->record_callback = callback;
    handle->user_data = pUserData;
    handle->buffer_capacity = SAMPLE_RATE * 10; // 10 seconds buffer
    handle->audio_buffer = (short *)malloc(handle->buffer_capacity * sizeof(short));
    handle->is_active = 1;
    handle->is_recording = 1;
    handle->start_time = clock();

    pthread_mutex_init(&handle->mutex, NULL);

    // Start timer thread
    pthread_create(&handle->timer_thread, NULL, timer_thread_func, handle);

    // Call start callback
    if (callback)
    {
        recordData_t record_data = {0};
        callback(handle, pUserData, STATUS_START, record_data);
    }

    printf("Recording started\n");
    return (HCLEVER)handle;
}

int recordStop(HCLEVER hclever)
{
    if (!hclever)
    {
        return STATUS_ERR_TIMEOUT;
    }

    voice_handle_t *handle = (voice_handle_t *)hclever;

    pthread_mutex_lock(&handle->mutex);
    handle->is_active = 0;
    handle->is_recording = 0;
    pthread_mutex_unlock(&handle->mutex);

    // Wait for timer thread to finish
    pthread_join(handle->timer_thread, NULL);

    // Call finish callback
    if (handle->record_callback)
    {
        recordData_t record_data = {0};
        record_data.nTimer = ((clock() - handle->start_time) * 1000) / CLOCKS_PER_SEC;
        handle->record_callback(handle, handle->user_data, STATUS_FINISH, record_data);
    }

    printf("Recording stopped\n");
    return STATUS_SUCCESS;
}
