package net.conczin.immersive_paintings.neoforge.compat;

import org.junit.jupiter.api.Test;

import javax.imageio.ImageIO;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Random;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MineAstrTranslationCompatTest {
    @Test
    void largeNoisyImageIsJpegWithinMineAstrLimit() throws Exception {
        BufferedImage source = new BufferedImage(4096, 2304, BufferedImage.TYPE_INT_ARGB);
        Random random = new Random(0x4d494e4541535452L);
        for (int y = 0; y < source.getHeight(); y++) {
            for (int x = 0; x < source.getWidth(); x++) {
                int rgb = random.nextInt() | 0xff000000;
                source.setRGB(x, y, rgb);
            }
        }

        byte[] encoded = MineAstrImageCodec.encodeForMineAstr(source);

        assertTrue(encoded.length > 0);
        assertTrue(encoded.length <= MineAstrImageCodec.MAX_IMAGE_BYTES);
        assertEquals(0xff, encoded[0] & 0xff);
        assertEquals(0xd8, encoded[1] & 0xff);
        BufferedImage decoded = ImageIO.read(new ByteArrayInputStream(encoded));
        assertNotNull(decoded);
        assertTrue(Math.max(decoded.getWidth(), decoded.getHeight())
                <= MineAstrImageCodec.MAX_IMAGE_DIMENSION);
    }

    @Test
    void transparentPixelsAreFlattenedOntoWhite() throws Exception {
        BufferedImage source = new BufferedImage(32, 32, BufferedImage.TYPE_INT_ARGB);
        source.setRGB(16, 16, new Color(255, 0, 0, 128).getRGB());

        BufferedImage decoded = ImageIO.read(new ByteArrayInputStream(
                MineAstrImageCodec.encodeForMineAstr(source)));

        Color corner = new Color(decoded.getRGB(0, 0));
        assertTrue(corner.getRed() > 245);
        assertTrue(corner.getGreen() > 245);
        assertTrue(corner.getBlue() > 245);
    }

    @Test
    void nullImageFailsClosed() {
        assertThrows(
                IOException.class,
                () -> MineAstrImageCodec.encodeForMineAstr(null));
    }

    @Test
    void languageSelectionPrefersExactThenFamily() {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("en_us", "US");
        values.put("zh-tw", "TW");
        values.put("zh_cn", "CN");

        assertEquals(
                "TW",
                MineAstrImageCodec.selectTranslation(values, "zh_tw"));
        assertEquals(
                "TW",
                MineAstrImageCodec.selectTranslation(values, "zh_hk"));
        assertEquals(
                "",
                MineAstrImageCodec.selectTranslation(values, "ja_jp"));
    }

    @Test
    void languageNormalizationMatchesMineAstrFormat() {
        assertEquals("zh_cn", MineAstrImageCodec.normalizeLanguage(" ZH-CN "));
        assertEquals("", MineAstrImageCodec.normalizeLanguage(null));
    }
}
