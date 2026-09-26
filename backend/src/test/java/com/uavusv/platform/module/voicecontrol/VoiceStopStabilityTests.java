package com.uavusv.platform.module.voicecontrol;
import java.nio.file.*;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.RepetitionInfo;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
@EnabledIfEnvironmentVariable(named = "P0_REAL_RUNNER", matches = ".+")
class VoiceStopStabilityTests extends VoiceRealRunnerTests {
 @RepeatedTest(10) void repeatedStopRetainsActualExitEvidence(RepetitionInfo info) throws Exception {
  try {realRunnerReadyHeartbeatAndFourActions();}
  finally {Files.copy(Path.of("target/p0-real-runner-report.json"),Path.of("target/stop-stability-"+info.getCurrentRepetition()+".json"),StandardCopyOption.REPLACE_EXISTING);}
 }
}
