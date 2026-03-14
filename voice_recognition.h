#ifndef VOICE_RECOGNITION_H
#define VOICE_RECOGNITION_H

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdint.h>

// Status codes
#define STATUS_SUCCESS 0
#define STATUS_ERR_NEEDMORESAMPLE 1
#define STATUS_ERR_TIMEOUT 2
#define STATUS_START 3
#define STATUS_FINISH 4
#define STATUS_TIMER 5
#define STATUS_STD 6
#define STATUS_RESULT 7
#define STATUS_SAMPLE 8

// Maximum word length
#define MAX_WORD_LEN 256

    // Recognition result structure
    typedef struct
    {
        unsigned long nTimer;      // Identify consumption time in milliseconds
        int nVolume;               // Current abdominal volume ranges from 0 to 32767
        int nCmdID;                // Identification result ID
        int nWordDura;             // Length of recognition result, measured in samples
        int nEndSil;               // Waiting length after recognition, measured in samples
        int nLatency;              // Recognition engine delay, in samples
        int nConfi;                // Confidence score, the higher the better
        int nSGDiff;               // Score difference between instruction and SG (Silence and Garbage)
        int nGMMappingID;          // Mapping ID corresponding to the instruction
        char pszCmd[MAX_WORD_LEN]; // String of recognition results
    } recogResult_t;

    // Record data structure
    typedef struct
    {
        unsigned long nTimer; // Recording time, measured in milliseconds
        int nVolume;          // Estimated volume at current time ranges from 0 to 32767
        short *psSamples;     // ECNR data
        int nSampleSize;      // ECNR data length
    } recordData_t;

    // Callback function types
    typedef int (*CALLBACK_Recognition)(void *handler, void *pUserData, int nStatus, recogResult_t sRecogResult);
    typedef int (*CALLBACK_Record)(void *handler, void *pUserData, int nStatus, recordData_t sRecordData);

    // Handle type
    typedef void *HCLEVER;

    // Main API functions
    int InitEx_WithLicense(const char *license_key);
    HCLEVER recogStart(CALLBACK_Recognition callback, void *pUserData);
    int addSample(HCLEVER hclever, short *ipsSample, int nNumSamples);
    int recogStop(HCLEVER hclever);
    recogResult_t getResult(HCLEVER hclever);
    int release(HCLEVER hclever);

    // Recording functions
    HCLEVER recordStart(CALLBACK_Record callback, void *pUserData);
    int recordStop(HCLEVER hclever);

    // Utility functions
    int detectSilence(short *samples, int numSamples, int threshold);
    int calculateVolume(short *samples, int numSamples);

#ifdef __cplusplus
}
#endif

#endif // VOICE_RECOGNITION_H