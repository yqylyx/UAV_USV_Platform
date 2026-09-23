package com.uavusv.platform.module.voicecontrol;
import java.nio.file.*;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.RepetitionInfo;
class VoiceStopStabilityTests extends VoiceRealRunnerTests {
 @RepeatedTest(10) void repeatedStopRetainsActualExitEvidence(RepetitionInfo info) throws Exception {
  try {realRunnerReadyHeartbeatAndFourActions();}
  finally {Files.copy(Path.of("target/p0-real-runner-report.json"),Path.of("target/stop-stability-"+info.getCurrentRepetition()+".json"),StandardCopyOption.REPLACE_EXISTING);}
 }
}
