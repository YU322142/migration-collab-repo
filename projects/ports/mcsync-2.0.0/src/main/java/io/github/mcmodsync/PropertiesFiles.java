package io.github.mcmodsync;

import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

final class PropertiesFiles {
    private static final byte[] UTF8_BOM = {(byte) 0xef, (byte) 0xbb, (byte) 0xbf};

    private PropertiesFiles() {
    }

    static Properties load(Path path) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        int offset = startsWithUtf8Bom(bytes) ? UTF8_BOM.length : 0;
        String text = new String(bytes, offset, bytes.length - offset, StandardCharsets.UTF_8);
        Properties properties = new Properties();
        properties.load(new StringReader(text));
        return properties;
    }

    private static boolean startsWithUtf8Bom(byte[] bytes) {
        return bytes.length >= UTF8_BOM.length
                && bytes[0] == UTF8_BOM[0]
                && bytes[1] == UTF8_BOM[1]
                && bytes[2] == UTF8_BOM[2];
    }
}
