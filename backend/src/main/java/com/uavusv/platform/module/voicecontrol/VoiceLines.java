package com.uavusv.platform.module.voicecontrol;

import java.io.*;
import java.nio.charset.StandardCharsets;

/** Oversized lines are drained with bounded memory and returned as an invalid event. */
public final class VoiceLines {
    private VoiceLines() {}

    public static String read(InputStream in) throws IOException {
        var bytes = new ByteArrayOutputStream();
        boolean oversized = false;
        int next;
        while ((next = in.read()) != -1 && next != '\n') {
            if (bytes.size() < 256 * 1024) bytes.write(next);
            else oversized = true;
        }
        if (next == -1 && bytes.size() == 0 && !oversized) return null;
        return oversized ? "{\"kind\":\"OVERSIZED_LINE\"}" : bytes.toString(StandardCharsets.UTF_8);
    }
}
