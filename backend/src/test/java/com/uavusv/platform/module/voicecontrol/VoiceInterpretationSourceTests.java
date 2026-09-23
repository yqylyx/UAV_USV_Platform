package com.uavusv.platform.module.voicecontrol;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.uavusv.platform.module.voiceintelligence.AsrFailure;
import com.uavusv.platform.module.voiceintelligence.IntentService;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class VoiceInterpretationSourceTests extends VoiceControlTests {
    IntentService intents;

    @BeforeEach
    void attachIntentSourceVerifier() {
        intents = mock(IntentService.class);
        app = new VoiceCommandApplicationService(s, j, t, a, r, settings, intents);
    }

    @Test
    void verifiedInterpretationIsLinkedToProposal() {
        String source = "11111111-1111-4111-8111-111111111111";
        var result = app.createProposal(VoiceJson.uuid(), source, request("PAUSE")).data();
        assertEquals(source, result.path("interpretationId").asText());
        verify(intents).requireCandidate(eq(1L), eq(source), eq("PAUSE"), any());
    }

    @Test
    void spoofedOrExpiredInterpretationIsRejected() {
        String source = "11111111-1111-4111-8111-111111111111";
        doThrow(new AsrFailure(409, "VOICE_INTERPRETATION_INVALID"))
                .when(intents)
                .requireCandidate(eq(1L), eq(source), eq("PAUSE"), any());
        VoiceFailure failure =
                assertThrows(
                        VoiceFailure.class,
                        () -> app.createProposal(VoiceJson.uuid(), source, request("PAUSE")));
        assertEquals("VOICE_INTERPRETATION_INVALID", failure.code);
    }

    @Test
    void interpretationIdParticipatesInProposalIdempotencyHash() {
        String key = VoiceJson.uuid();
        app.createProposal(
                key, "11111111-1111-4111-8111-111111111111", request("PAUSE"));
        VoiceFailure failure =
                assertThrows(
                        VoiceFailure.class,
                        () ->
                                app.createProposal(
                                        key,
                                        "22222222-2222-4222-8222-222222222222",
                                        request("PAUSE")));
        assertEquals("IDEMPOTENCY_CONFLICT", failure.code);
    }
}
