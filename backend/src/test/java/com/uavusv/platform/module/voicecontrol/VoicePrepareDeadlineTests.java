package com.uavusv.platform.module.voicecontrol;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.nio.file.*;
import java.util.*;
import com.uavusv.platform.module.mission.service.*;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import org.springframework.test.util.ReflectionTestUtils;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
class VoicePrepareDeadlineTests extends VoiceControlTests {
 @ParameterizedTest @ValueSource(strings={"separate_windows","ready_timeout"})
 void actualPrepareUsesSeparateSixtySecondDeadlines(String scenario) throws Exception { checkScenario(scenario); }
 @org.junit.jupiter.api.Test void initialFrameHasItsOwnDeadline() throws Exception { checkScenario("frame_timeout"); }
 private void checkScenario(String scenario) throws Exception {
  var manager=new AlgorithmRuntimeManager(j.mapper,mock(MissionRunRepository.class),mock(AlgorithmCatalogService.class),System.getenv().getOrDefault("PYTHON_COMMAND", "python"),repositoryFile("backend/src/test/resources/voicecontrol/contract_runner.py").toString());
  ReflectionTestUtils.setField(manager,"voiceBridge",new VoiceRuntimeBridge(r,app,worker,j));
  Map<String,Object> config=new HashMap<>();config.put("standaloneVirtualSimulation",true);
  config.put("testReadyDelaySeconds",scenario.equals("separate_windows")?58:scenario.equals("ready_timeout")?62:0);
  config.put("testFrameDelaySeconds",scenario.equals("separate_windows")?58:scenario.equals("frame_timeout")?62:0);
  long started=System.nanoTime();
  try {
   if(scenario.equals("separate_windows")){var prepared=manager.prepare(990081L,"GB_SFLA_CS",config);assertNotNull(prepared.runtimeRef());assertNotNull(prepared.latestFrame());assertTrue((System.nanoTime()-started)/1e9>110);}
   else {var failure=assertThrows(com.uavusv.platform.common.exception.BusinessException.class,()->manager.prepare(990081L,"GB_SFLA_CS",config));assertEquals(scenario.equals("ready_timeout")?"算法运行器启动超时":"Algorithm initial frame timeout",failure.getMessage());assertTrue((System.nanoTime()-started)/1e9>=59);assertTrue(((Map<?,?>)ReflectionTestUtils.getField(manager,"handles")).isEmpty());}
   Files.writeString(Path.of("target/prepare-deadline-"+scenario+".json"),j.object().put("scenario",scenario).put("elapsedSeconds",(System.nanoTime()-started)/1e9).put("result","PASS").toPrettyString());
  } finally {manager.close();}
 }
}
