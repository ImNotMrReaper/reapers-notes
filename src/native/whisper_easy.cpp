#include "whisper.h"
#include <cstdlib>
#include <cstring>

extern "C" {

struct whisper_context * easy_init(const char * model_path) {
    struct whisper_context_params cparams = whisper_context_default_params();
    cparams.use_gpu = true; // Enable Intel iGPU (Vulkan) acceleration
    return whisper_init_from_file_with_params(model_path, cparams);
}

void easy_free(struct whisper_context * ctx) {
    if (ctx) {
        whisper_free(ctx);
    }
}

char * easy_transcribe(struct whisper_context * ctx, const float * samples, int n_samples, int n_threads, const char * prompt) {
    if (!ctx || !samples || n_samples <= 0) {
        return strdup("");
    }

    struct whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.n_threads = (n_threads > 0) ? n_threads : 4;
    params.no_timestamps = true;
    params.no_context = true;
    params.single_segment = false;
    params.print_special = false;
    params.print_progress = false;
    params.print_realtime = false;
    params.print_timestamps = false;
    params.language = "en";
    params.suppress_blank = true;
    params.suppress_nst = true;

    if (prompt && prompt[0]) {
        params.initial_prompt = prompt;
    }

    if (whisper_full(ctx, params, samples, n_samples) != 0) {
        return strdup("");
    }

    int n_seg = whisper_full_n_segments(ctx);
    size_t total_len = 0;
    for (int i = 0; i < n_seg; ++i) {
        total_len += strlen(whisper_full_get_segment_text(ctx, i)) + 1;
    }

    char * res = (char *)malloc(total_len + 1);
    if (!res) {
        return strdup("");
    }
    res[0] = '\0';
    for (int i = 0; i < n_seg; ++i) {
        strcat(res, whisper_full_get_segment_text(ctx, i));
    }
    return res;
}

void easy_free_string(char * str) {
    if (str) {
        free(str);
    }
}

}
