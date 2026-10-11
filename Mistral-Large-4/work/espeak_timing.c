/*
 * espeak_timing.c — synthesize a text file through libespeak-ng with phoneme
 * events enabled, and dump the synthesis event stream (word / sentence /
 * phoneme boundaries, in milliseconds of the generated audio) plus the raw
 * 16-bit mono audio. This gives sample-accurate alignment data straight from
 * the synthesizer, with no envelope estimation.
 *
 * usage: espeak_timing <text-file> <speed-wpm> <pitch> <events-out> <raw-out>
 *          [voice]   (default en-us)
 *
 * Build (nix): gcc -O2 -I<espeak-ng>/include -o espeak_timing espeak_timing.c \
 *              -L<espeak-ng>/lib -lespeak-ng -Wl,-rpath,<espeak-ng>/lib
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <espeak-ng/speak_lib.h>

static short *audio = NULL;
static long audio_len = 0, audio_cap = 0;
static FILE *evf = NULL;

static int SynthCallback(short *wav, int numsamples, espeak_EVENT *events)
{
    if (wav && numsamples > 0) {
        if (audio_len + numsamples > audio_cap) {
            audio_cap = (audio_len + numsamples) * 2 + 65536;
            audio = (short *)realloc(audio, (size_t)audio_cap * sizeof(short));
            if (!audio) {
                fprintf(stderr, "out of memory\n");
                return 1;
            }
        }
        memcpy(audio + audio_len, wav, (size_t)numsamples * sizeof(short));
        audio_len += numsamples;
    }
    if (events) {
        int i;
        for (i = 0; events[i].type != espeakEVENT_LIST_TERMINATED; i++) {
            espeak_EVENT *e = &events[i];
            char idbuf[9];
            const char *id = "";
            if (e->type == espeakEVENT_PHONEME) {
                memcpy(idbuf, e->id.string, 8);
                idbuf[8] = 0;
                id = idbuf;
            } else if (e->type == espeakEVENT_MARK
                       || e->type == espeakEVENT_PLAY) {
                id = e->id.name ? e->id.name : "";
            }
            fprintf(evf, "%d %d %d %d %s\n", (int)e->type, e->text_position,
                    e->length, e->audio_position, id);
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    FILE *f, *rf;
    char *text;
    long fsize, tlen;
    int speed, pitch, rate;
    espeak_ERROR err;

    if (argc < 6) {
        fprintf(stderr, "usage: %s <text-file> <speed-wpm> <pitch> "
                "<events-out> <raw-out>\n", argv[0]);
        return 2;
    }
    f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    text = (char *)malloc((size_t)fsize + 1);
    if (fread(text, 1, (size_t)fsize, f) != (size_t)fsize) {
        fprintf(stderr, "read failed\n");
        return 1;
    }
    fclose(f);
    text[fsize] = 0;
    /* strip leading/trailing whitespace, like the python pipeline does */
    {
        char *s = text, *e = text + strlen(text);
        while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r')
            s++;
        while (e > s && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\n'
                         || e[-1] == '\r'))
            e--;
        memmove(text, s, (size_t)(e - s));
        text[e - s] = 0;
    }
    tlen = (long)strlen(text);
    speed = atoi(argv[2]);
    pitch = atoi(argv[3]);
    const char *voice = argc > 6 ? argv[6] : "en-us";
    evf = fopen(argv[4], "w");
    if (!evf) {
        fprintf(stderr, "cannot open %s\n", argv[4]);
        return 1;
    }

    rate = espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, NULL,
                             espeakINITIALIZE_PHONEME_EVENTS);
    if (rate < 0) {
        fprintf(stderr, "espeak_Initialize failed\n");
        return 1;
    }
    espeak_SetSynthCallback(SynthCallback);
    if (espeak_SetVoiceByName(voice) != EE_OK) {
        fprintf(stderr, "SetVoiceByName(%s) failed\n", voice);
        return 1;
    }
    espeak_SetParameter(espeakRATE, speed, 0);
    espeak_SetParameter(espeakPITCH, pitch, 0);
    /* espeakENDPAUSE matches the espeak-ng CLI default (sentence pause at
     * the end of the text), so the generated audio is identical to the
     * CLI-produced WAV used for the delivered dialogue.wav. */
    err = espeak_Synth(text, (size_t)tlen + 1, 0, POS_CHARACTER, 0,
                       espeakCHARS_UTF8 | espeakENDPAUSE, NULL, NULL);
    if (err != EE_OK) {
        fprintf(stderr, "espeak_Synth failed (%d)\n", (int)err);
        return 1;
    }
    rf = fopen(argv[5], "wb");
    if (!rf) {
        fprintf(stderr, "cannot open %s\n", argv[5]);
        return 1;
    }
    if (audio_len > 0)
        fwrite(audio, sizeof(short), (size_t)audio_len, rf);
    fclose(rf);
    fprintf(evf, "AUDIO %d %ld %.6f\n", rate, audio_len,
            (double)audio_len / (double)rate);
    fclose(evf);
    fprintf(stderr, "espeak_timing: rate=%d samples=%ld duration=%.3f s\n",
            rate, audio_len, (double)audio_len / (double)rate);
    return 0;
}
