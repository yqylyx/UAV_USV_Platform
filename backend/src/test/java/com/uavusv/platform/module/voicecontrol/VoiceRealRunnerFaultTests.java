package com.uavusv.platform.module.voicecontrol;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.service.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.*;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Real Python adapter with test-only pipe faults, isolated H2 and accelerated Java test clock. */
@EnabledIfEnvironmentVariable(named="P0_REAL_RUNNER", matches=".+")
class VoiceRealRunnerFaultTests extends VoiceControlTests {
    AlgorithmRuntimeManager manager;
    Path trace;
    String runtime;
    void waitFor(BooleanSupplier condition) throws Exception {
        long end=System.nanoTime()+15_000_000_000L;
        while(!condition.getAsBoolean()) {
            if(System.nanoTime()>end) fail("Timed out; inspect "+trace);
            Thread.sleep(25);
        }
    }
    void start(String mode) throws Exception {
        trace=Path.of("target/fault-"+mode+"-"+UUID.randomUUID()+".jsonl").toAbsolutePath();
        Files.createFile(trace);
        manager=new AlgorithmRuntimeManager(j.mapper,mock(MissionRunRepository.class),mock(AlgorithmCatalogService.class),
            System.getenv().getOrDefault("PYTHON_COMMAND","python"),
            repositoryFile("backend/src/test/resources/voicecontrol/real_runner_fault_proxy.py").toString());
        ReflectionTestUtils.setField(manager,"voiceBridge",new VoiceRuntimeBridge(r,app,worker,j));
        var prepared=manager.prepare(990041L,"GB_SFLA_CS",Map.<String,Object>of(
            "standaloneVirtualSimulation",true,"seed",42,"faultMode",mode,"faultTrace",trace.toString()));
        runtime=prepared.runtimeRef();
        waitFor(()->r.channel(runtime).heartbeatNanos!=null);
    }
    List<ObjectNode> traceEvents() {
        try {
            var rows=new ArrayList<ObjectNode>();
            for(String line:Files.readAllLines(trace)) {
                try { rows.add(j.read(line)); } catch(Exception incomplete) { /* concurrent last line */ }
            }
            return rows;
        } catch(Exception e){throw new RuntimeException(e);}
    }
    long sentCommands(){return traceEvents().stream().filter(x->x.path("direction").asText().equals("java_to_runner") && x.path("event").path("kind").asText().equals("COMMAND")).count();}
    ObjectNode startCommand() {
        var e=execution(app.manual(runtime,"START"));worker.tick();return e;
    }
    String state(ObjectNode e){return app.execution(e.path("executionId").asText()).path("state").asText();}
    void save(String scenario) throws Exception {
        var report=j.object().put("scenario",scenario).put("runtimeRef",runtime).put("trace",trace.toString());
        report.set("context",app.context(runtime));
        report.set("executions",j.mapper.valueToTree(s.locked(()->s.query("SELECT data_json FROM voice_execution WHERE runtime_ref=?",runtime))));
        j.mapper.writerWithDefaultPrettyPrinter().writeValue(Path.of("target/fault-"+scenario+".json").toFile(),report);
    }
    @Test void crashMarksRuntimeLostAndOutcomeUnknown() throws Exception {
        try {
            start("crash_after_accept");var e=startCommand();
            waitFor(()->app.context(runtime).path("state").asText().equals("LOST"));
            assertEquals("TIMED_OUT",state(e));
            assertEquals("UNKNOWN",app.execution(e.path("executionId").asText()).path("outcome").asText());
            error("RUNTIME_UNAVAILABLE",()->app.manual(runtime,"STOP"));
            assertEquals(1,sentCommands());save("crash");
        } finally {if(manager!=null)manager.close();}
    }
    @Test void missingHeartbeatBlocksCommandsWithoutKillingRunner() throws Exception {
        try {
            start("silence_heartbeat");
            waitFor(()->traceEvents().stream().filter(x->x.path("event").path("kind").asText().equals("HEARTBEAT")).count()>=2);
            t.advance(5001);
            assertTrue(r.channel(runtime).alive.getAsBoolean());
            error("RUNTIME_UNAVAILABLE",()->app.manual(runtime,"START"));
            assertEquals(0,sentCommands());save("heartbeat");
        } finally {if(manager!=null)manager.close();}
    }
    @Test void realStatusQueryRecoversDroppedSuccessWithoutResend() throws Exception {
        try {
            start("delay_success");var e=startCommand();
            waitFor(()->state(e).equals("ACCEPTED"));
            waitFor(()->traceEvents().stream().anyMatch(x->x.path("event").path("status").asText().equals("SUCCEEDED")));
            t.advance(15001);worker.tick();
            waitFor(()->state(e).equals("SUCCEEDED"));
            assertFalse(app.execution(e.path("executionId").asText()).path("timedOutAt").isNull());
            assertTrue(traceEvents().stream().anyMatch(x->x.path("event").path("kind").asText().equals("STATUS_REPLY") && x.path("event").path("known").asBoolean()));
            var late=traceEvents().stream().filter(x->x.path("event").path("status").asText().equals("SUCCEEDED")).findFirst().orElseThrow().path("event");
            worker.receive(runtime,app.context(runtime).path("runtimeGeneration").asText(),late);
            assertEquals(1,sentCommands());
            assertEquals(1,app.context(runtime).path("stateVersion").asInt());
            assertEquals(2,s.jdbc.queryForObject("SELECT COUNT(*) FROM voice_command_event WHERE execution_id=?",Integer.class,e.path("executionId").asText()));
            save("query-recovery");
        } finally {if(manager!=null)manager.close();}
    }
    @Test void restartRejectsOldGenerationCommandAndReceipt() throws Exception {
        try {
            start("normal");var e=startCommand();waitFor(()->state(e).equals("SUCCEEDED"));
            String oldRef=runtime, oldGen=app.context(runtime).path("runtimeGeneration").asText();
            var oldCommand=traceEvents().stream().filter(x->x.path("direction").asText().equals("java_to_runner") && x.path("event").path("kind").asText().equals("COMMAND")).findFirst().orElseThrow().path("event").deepCopy();
            var oldResult=traceEvents().stream().filter(x->x.path("event").path("status").asText().equals("SUCCEEDED")).findFirst().orElseThrow().path("event").deepCopy();
            manager.close();start("normal");
            assertNotEquals(oldRef,runtime);assertNotEquals(oldGen,app.context(runtime).path("runtimeGeneration").asText());
            worker.receive(runtime,oldGen,oldResult);
            r.frame(runtime,oldGen,j.read("{\"sequence\":99999,\"agents\":[{\"deviceCode\":\"OLD\"}]}"));
            assertEquals("PREPARED",app.context(runtime).path("state").asText());
            assertEquals(0,app.context(runtime).path("stateVersion").asInt());
            assertTrue(app.context(runtime).path("latestFrameSequence").asLong()<99999);
            var current=startCommand();waitFor(()->state(current).equals("SUCCEEDED"));
            assertEquals(1,app.context(runtime).path("stateVersion").asInt());
            r.channel(runtime).sender.accept(oldCommand);
            waitFor(()->r.channel(runtime).faulted);
            assertTrue(traceEvents().stream().anyMatch(x->x.path("event").path("errorCode").asText().equals("IDENTITY_MISMATCH")));
            assertEquals("RUNNING",app.context(runtime).path("state").asText());
            assertEquals(1,app.context(runtime).path("stateVersion").asInt());
            error("RUNTIME_UNAVAILABLE",()->app.manual(runtime,"PAUSE"));
            save("generation");
        } finally {if(manager!=null)manager.close();}
    }
    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings={"stop_eof_before_ack","stop_eof_before_result"})
    void stopEofCannotFabricateSuccessOrResend(String mode) throws Exception {
        try {
            start(mode);var started=startCommand();waitFor(()->state(started).equals("SUCCEEDED"));
            var stopped=execution(app.manual(runtime,"STOP"));worker.tick();
            waitFor(()->!r.channel(runtime).alive.getAsBoolean());
            waitFor(()->state(stopped).equals("TIMED_OUT"));
            var status=app.execution(stopped.path("executionId").asText());
            assertEquals("UNKNOWN",status.path("outcome").asText());
            assertEquals("LOST",app.context(runtime).path("state").asText());
            assertEquals(0,s.jdbc.queryForObject("SELECT COUNT(*) FROM voice_command_event WHERE execution_id=? AND data_json LIKE '%SUCCEEDED%'",Integer.class,stopped.path("executionId").asText()));
            assertEquals(2,sentCommands());
            for(int i=0;i<5;i++){t.advance(16000);worker.tick();}
            assertEquals(2,sentCommands());
            assertEquals("TIMED_OUT",state(stopped));save(mode);
        } finally {if(manager!=null)manager.close();}
    }
    @Test void realManagerCleanupPreservesUnknownExecutionAndReceipts() throws Exception {
        try {
            start("delay_success");var e=startCommand();waitFor(()->state(e).equals("ACCEPTED"));
            int commands=count("voice_execution"),receipts=count("voice_command_event"),keys=count("voice_idempotency");
            manager.close();waitFor(()->!r.channel(runtime).alive.getAsBoolean());
            assertEquals("TIMED_OUT",state(e));assertEquals("UNKNOWN",app.execution(e.path("executionId").asText()).path("outcome").asText());
            worker.recover();worker.tick();manager.close();
            assertEquals(commands,count("voice_execution"));assertEquals(receipts,count("voice_command_event"));assertEquals(keys,count("voice_idempotency"));
            assertEquals(1,sentCommands());save("manager-cleanup");
        } finally {if(manager!=null)manager.close();}
    }
    @Test void blockedActualWorkerStopsHeartbeatsWithoutInventingResult() throws Exception {
        try {
            start("worker_deadlock");var e=startCommand();waitFor(()->state(e).equals("ACCEPTED"));
            long beats=traceEvents().stream().filter(x->x.path("event").path("kind").asText().equals("HEARTBEAT")).count();
            Thread.sleep(5500);
            assertTrue(r.channel(runtime).alive.getAsBoolean());
            assertEquals(beats,traceEvents().stream().filter(x->x.path("event").path("kind").asText().equals("HEARTBEAT")).count());
            assertFalse(traceEvents().stream().anyMatch(x->x.path("event").path("status").asText().equals("SUCCEEDED")));
            t.advance(5501);error("RUNTIME_UNAVAILABLE",()->app.manual(runtime,"STOP"));
            t.advance(10000);worker.tick();assertEquals("TIMED_OUT",state(e));
            assertEquals("UNKNOWN",app.execution(e.path("executionId").asText()).path("outcome").asText());assertEquals(1,sentCommands());save("worker-deadlock");
        } finally {if(manager!=null)manager.close();}
    }
    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings={"oversized_lines","wrong_identity_lines","ordinary_logs"})
    void threeInvalidStdoutLinesProtectChannelWithoutExecution(String mode) throws Exception {
        try {
            start(mode);waitFor(()->r.channel(runtime).faulted);
            assertTrue(r.channel(runtime).alive.getAsBoolean());
            assertEquals("PREPARED",app.context(runtime).path("state").asText());
            assertEquals(0,app.context(runtime).path("stateVersion").asInt());
            error("RUNTIME_UNAVAILABLE",()->app.manual(runtime,"START"));
            assertEquals(0,sentCommands());
            assertEquals(0,count("voice_execution"));assertEquals(0,count("voice_command_event"));save(mode);
        } finally {if(manager!=null)manager.close();}
    }
    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings={"confirm_many","confirm_cancel"})
    void realAdapterAppliesAtMostOnceUnderConcurrentProposalWrites(String mode) throws Exception {
        var pool=java.util.concurrent.Executors.newFixedThreadPool(12);
        try {
            start("apply_count");r.channel(runtime).sceneNanos=t.nanos();
            var context=app.context(runtime);
            var p=app.createProposal(VoiceJson.uuid(),j.object().put("runtimeRef",runtime).put("runtimeGeneration",context.path("runtimeGeneration").asText()).put("expectedContextVersion",context.path("contextVersion").asLong()).put("intent","MISSION_START")).data();
            var gate=new java.util.concurrent.CountDownLatch(1);
            var futures=new ArrayList<java.util.concurrent.Future<String>>();
            int n=mode.equals("confirm_many")?12:2;
            for(int index=0;index<n;index++) {
                final boolean cancel=mode.equals("confirm_cancel")&&index==1;
                futures.add(pool.submit(()->{login("alice");try{gate.await();if(cancel){app.cancel(p.path("proposalId").asText(),VoiceJson.uuid(),confirmation(p));return "CANCELLED";}return execution(confirm(p)).path("executionId").asText();}catch(VoiceFailure e){return e.code;}finally{org.springframework.security.core.context.SecurityContextHolder.clearContext();}}));
            }
            gate.countDown();var outcomes=new ArrayList<String>();for(var f:futures)outcomes.add(f.get(10,java.util.concurrent.TimeUnit.SECONDS));
            if(mode.equals("confirm_many"))assertEquals(1,new HashSet<>(outcomes).size());
            worker.tick();
            int executions=count("voice_execution");assertTrue(executions<=1);
            if(executions==1)waitFor(()->app.context(runtime).path("state").asText().equals("RUNNING"));
            assertEquals(executions,count("voice_outbox"));assertEquals(executions,sentCommands());
            var applies=Files.readAllLines(Path.of(trace.toString()+".apply.jsonl")).stream().map(j::read).filter(x->x.path("active").asBoolean()).count();
            assertEquals(executions,applies);
            if(mode.equals("confirm_many")){assertEquals(1,executions);assertEquals(1,applies);}
            if(mode.equals("confirm_cancel")){assertTrue(outcomes.contains("ALREADY_CONFIRMED")||outcomes.contains("CANCELLED"));}
            save("concurrent-"+mode);
            Files.writeString(Path.of("target/concurrent-"+mode+"-counts.json"),j.object().put("executions",executions).put("actualAdapterStarts",applies).put("sentCommands",sentCommands()).set("outcomes",j.mapper.valueToTree(outcomes)).toPrettyString());
        } finally {pool.shutdownNow();if(manager!=null)manager.close();}
    }
    @Test void lateRealOldResultReconcilesOnlyOldExecutionAfterReplacement() throws Exception {
        try {
            start("delay_success");var old=startCommand();waitFor(()->state(old).equals("ACCEPTED"));
            waitFor(()->traceEvents().stream().anyMatch(x->x.path("event").path("status").asText().equals("SUCCEEDED")));
            var success=traceEvents().stream().filter(x->x.path("event").path("status").asText().equals("SUCCEEDED")).findFirst().orElseThrow().path("event").deepCopy();
            var accepted=traceEvents().stream().filter(x->x.path("event").path("status").asText().equals("ACCEPTED")).findFirst().orElseThrow().path("event").deepCopy();
            String oldRef=runtime,oldGen=app.context(runtime).path("runtimeGeneration").asText();Path oldTrace=trace;
            manager.close();waitFor(()->!r.channel(oldRef).alive.getAsBoolean());
            for(int n=0;n<4;n++){t.advance(16000);worker.tick();}
            assertEquals("TIMED_OUT",state(old));assertEquals("UNKNOWN",app.execution(old.path("executionId").asText()).path("outcome").asText());
            assertFalse(traceEvents().stream().anyMatch(x->x.path("direction").asText().equals("java_to_runner")&&x.path("event").path("kind").asText().equals("STATUS_QUERY")));
            start("normal");var before=app.context(runtime).deepCopy();
            worker.receive(oldRef,oldGen,success);assertEquals("SUCCEEDED",state(old));
            worker.receive(oldRef,oldGen,accepted);assertEquals("SUCCEEDED",state(old));
            assertEquals(before,app.context(runtime));assertEquals(0,sentCommands());
            save("late-old-result");Files.writeString(Path.of("target/late-old-execution.json"),app.execution(old.path("executionId").asText()).toPrettyString());
            Files.writeString(Path.of("target/late-old-trace-path.txt"),oldTrace.toString());
        } finally {if(manager!=null)manager.close();}
    }
    @Test void replacingRealProcessInvalidatesOldProposalWithoutWritingNewProcess() throws Exception {
        try {
            start("normal");r.channel(runtime).sceneNanos=t.nanos();var old=app.context(runtime);
            var p=app.createProposal(VoiceJson.uuid(),j.object().put("runtimeRef",runtime).put("runtimeGeneration",old.path("runtimeGeneration").asText()).put("expectedContextVersion",old.path("contextVersion").asLong()).put("intent","MISSION_START")).data();
            manager.close();start("normal");
            assertNotEquals(old.path("runtimeGeneration"),app.context(runtime).path("runtimeGeneration"));
            assertEquals("INVALIDATED",app.proposal(p.path("proposalId").asText()).path("status").asText());
            error("PROPOSAL_INVALIDATED",()->confirm(p));worker.tick();
            assertEquals(0,sentCommands());assertEquals(0,count("voice_execution"));save("old-proposal-replacement");
        } finally {if(manager!=null)manager.close();}
    }
}


