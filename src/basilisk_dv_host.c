/* Host adapter for an unmodified Basilisk dvAccumulation module. */
#include "fswAlgorithms/transDetermination/dvAccumulation/dvAccumulation.h"

#include <stddef.h>
#include <stdlib.h>

DVAccumulationData *dv_create(void) {
    DVAccumulationData *state = calloc(1, sizeof(*state));
    if (state != NULL) {
        SelfInit_dvAccumulation(state, 0);
        Reset_dvAccumulation(state, 0, 0);
    }
    return state;
}

void dv_destroy(DVAccumulationData *state) {
    free(state);
}

int dv_push(DVAccumulationData *state, const uint64_t *time_ns, const double *acceleration,
            size_t count, double *delta_v) {
    if (count == 0 || count > MAX_ACC_BUF_PKT) {
        return 1;
    }
    state->accPktInMsg.payload = (AccDataMsgPayload){0};
    for (size_t i = 0; i < count; ++i) {
        AccPktDataMsgPayload *packet = &state->accPktInMsg.payload.accPkts[i];
        packet->measTime = time_ns[i];
        for (size_t j = 0; j < 3; ++j) {
            packet->accel_B[j] = acceleration[3 * i + j];
        }
    }
    Update_dvAccumulation(state, time_ns[count - 1], 0);
    for (size_t j = 0; j < 3; ++j) {
        delta_v[j] = state->dvAcumOutMsg.payload.vehAccumDV[j];
    }
    return 0;
}
