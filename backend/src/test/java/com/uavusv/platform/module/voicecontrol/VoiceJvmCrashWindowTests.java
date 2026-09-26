package com.uavusv.platform.module.voicecontrol;
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@EnabledIfEnvironmentVariable(named="P0_REAL_RUNNER", matches=".+")
class VoiceJvmCrashWindowTests extends VoiceControlTests {
 String database;
 @Override javax.sql.DataSource dataSource() {
  if(database==null)return super.dataSource();
  var ds=new JdbcDataSource();ds.setURL("jdbc:h2:file:"+database+";MODE=MySQL;WRITE_DELAY=0");return ds;
 }
 public static void main(String[] args) throws Exception {
  var test=new VoiceJvmCrashWindowTests();test.database=args[1];test.setup();
  String mode=args[0];Path output=Path.of(args[2]);
  test.s.locked(()->{var c=test.s.get("voice_runtime_context",test.ref());c.put("state","PREPARED").put("stateVersion",0);test.s.save("voice_runtime_context",c);return null;});
  Process runner=new ProcessBuilder(System.getenv().getOrDefault("PYTHON_COMMAND", "python"),System.getenv("P0_REAL_RUNNER"),"--algorithm","GB_SFLA_CS","--run-id","990051","--config-base64","eyJzZWVkIjo0Mn0=","--command-protocol","v1","--runtime-ref",test.ref(),"--runtime-generation",test.gen())
    .redirectError(output.resolve("runner.stderr.log").toFile()).start();
  Files.writeString(output.resolve("runner.pid"),Long.toString(runner.pid()));
  var reader=runner.inputReader(java.nio.charset.StandardCharsets.UTF_8);
  String line;while((line=reader.readLine())!=null){Files.writeString(output.resolve("runner.stdout.jsonl"),line+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);if(line.contains("RUNTIME_READY"))break;}
  var writer=runner.outputWriter(java.nio.charset.StandardCharsets.UTF_8);
  test.r.attach(test.ref(),test.gen(),command->{
   try {
    assertEquals("SENDING",test.s.jdbc.queryForObject("SELECT status FROM voice_outbox",String.class));
    Files.writeString(output.resolve("boundary.json"),test.j.object().put("mode",mode).put("jvmPid",ProcessHandle.current().pid()).put("runtimeRef",test.ref()).put("commandId",command.path("commandId").asText()).put("outbox","SENDING").toString());
    if(mode.equals("before_write"))Runtime.getRuntime().halt(73);
    writer.write(command.toString());writer.newLine();writer.flush();
    Files.writeString(output.resolve("flush-completed.json"),command.toString());
    String receipt;
    while((receipt=reader.readLine())!=null){
     Files.writeString(output.resolve("runner.stdout.jsonl"),receipt+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
     if(receipt.contains("SUCCEEDED"))break;
    }
    assertNotNull(receipt,"No real success before crash");
    assertEquals("SENDING",test.s.jdbc.queryForObject("SELECT status FROM voice_outbox",String.class));
    Runtime.getRuntime().halt(74);
   }catch(IOException error){throw new RuntimeException(error);}
  },runner::isAlive);
  test.r.channel(test.ref()).heartbeatNanos=test.t.nanos();test.r.channel(test.ref()).sceneNanos=test.t.nanos();
  test.confirm(test.proposal("START"));test.worker.tick();throw new AssertionError("Crash boundary not reached");
 }
 @ParameterizedTest @ValueSource(strings={"before_write","after_flush"})
 void realJvmCrashRetainsUncertainOutboxWithoutReplay(String mode) throws Exception {
  Path output=Path.of("target","jvm-crash-"+mode+"-"+UUID.randomUUID()).toAbsolutePath();Files.createDirectories(output);
  String db=output.resolve("database").toString().replace('\\','/');
  var child=new ProcessBuilder(Path.of(System.getProperty("java.home"),"bin","java.exe").toString(),"-cp",System.getProperty("java.class.path"),getClass().getName(),mode,db,output.toString())
   .redirectOutput(output.resolve("jvm.stdout.log").toFile()).redirectError(output.resolve("jvm.stderr.log").toFile()).start();
  try {
   assertTrue(child.waitFor(35,TimeUnit.SECONDS),"Child did not reach crash barrier: "+output);
   assertEquals(mode.equals("before_write")?73:74,child.exitValue(),"Child output: "+output);
   var ds=new JdbcDataSource();ds.setURL("jdbc:h2:file:"+db+";MODE=MySQL;WRITE_DELAY=0");
   var jdbc=new JdbcTemplate(ds);var store=new VoiceStore(jdbc,new DataSourceTransactionManager(ds),j);
   assertEquals("SENDING",jdbc.queryForObject("SELECT status FROM voice_outbox",String.class));
   var before=store.query("SELECT data_json FROM voice_execution").get(0);
   Files.writeString(output.resolve("before-recovery.json"),before.toPrettyString());
   var access=new VoiceAccess(jdbc);var registry=new RuntimeContextRegistry(store,j,t,access,settings);var dispatcher=new VoiceDispatcher(store,j,t,registry);
   dispatcher.recover();dispatcher.tick();dispatcher.recover();dispatcher.tick();
   var after=store.query("SELECT data_json FROM voice_execution").get(0);
   assertEquals("TIMED_OUT",after.path("state").asText());assertEquals("UNKNOWN",after.path("outcome").asText());
   assertEquals(before.path("commandId"),after.path("commandId"));assertEquals("UNCERTAIN",jdbc.queryForObject("SELECT status FROM voice_outbox",String.class));
   assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM voice_execution",Integer.class));assertTrue(registry.channels.isEmpty());
   assertEquals(mode.equals("after_flush"),Files.exists(output.resolve("flush-completed.json")));
   Files.writeString(output.resolve("after-recovery.json"),after.toPrettyString());
   Files.writeString(output.resolve("result.json"),j.object().put("result","PASS").put("mode",mode).put("exitCode",child.exitValue()).put("storage","file H2, not MySQL").toPrettyString());
  } finally {
   if(child.isAlive())child.destroyForcibly();
   Path pid=output.resolve("runner.pid");if(Files.exists(pid))ProcessHandle.of(Long.parseLong(Files.readString(pid))).ifPresent(p->{if(p.isAlive())p.destroy();});
  }
 }
}
