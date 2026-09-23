package com.uavusv.platform.module.voicecontrol;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import com.uavusv.platform.module.mission.controller.AlgorithmRuntimeController;
import com.uavusv.platform.module.mission.service.AlgorithmRuntimeManager;
class VoiceRunIdBoundaryTests {
 @ParameterizedTest @ValueSource(strings={"9223372036854775808","-9223372036854775809","18446744073709551615"})
 void oversizedIdNeverReachesManager(String value) throws Exception {
  var manager=mock(AlgorithmRuntimeManager.class);
  var mvc=MockMvcBuilders.standaloneSetup(new AlgorithmRuntimeController(manager)).build();
  mvc.perform(get("/api/algorithm-runs/"+value+"/status")).andExpect(status().isBadRequest());
  mvc.perform(post("/api/algorithm-runs/"+value+"/stop")).andExpect(status().isBadRequest());
  verifyNoInteractions(manager);
 }
 @ParameterizedTest @ValueSource(longs={9001L,9223372036854775807L})
 void validIdReachesManagerWithoutTruncation(long value) throws Exception {
  var manager=mock(AlgorithmRuntimeManager.class);
  var mvc=MockMvcBuilders.standaloneSetup(new AlgorithmRuntimeController(manager)).build();
  mvc.perform(get("/api/algorithm-runs/"+value+"/status")).andExpect(status().isOk());
  verify(manager).status(value);verifyNoMoreInteractions(manager);
 }
}
