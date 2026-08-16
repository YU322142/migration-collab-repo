package net.conczin.immersive_paintings.neoforge.compat;

import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.stream.MemoryCacheImageOutputStream;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Locale;
import java.util.Map;

/** Pure-Java image and language helpers used by the client bridge. */
public final class MineAstrImageCodec {
    public static final int MAX_IMAGE_BYTES = 768 * 1024;
    public static final int MAX_IMAGE_DIMENSION = 2048;

    private MineAstrImageCodec() {
    }

    public static byte[] encodeForMineAstr(BufferedImage source) throws IOException {
        if (source == null || source.getWidth() <= 0 || source.getHeight() <= 0) {
            throw new IOException("Painting image is empty");
        }

        float initialScale = Math.min(
                1.0F,
                (float) MAX_IMAGE_DIMENSION / Math.max(source.getWidth(), source.getHeight()));
        int width = Math.max(1, Math.round(source.getWidth() * initialScale));
        int height = Math.max(1, Math.round(source.getHeight() * initialScale));
        float[] qualities = {0.90F, 0.76F, 0.62F, 0.48F, 0.34F, 0.22F};

        for (int resizeAttempt = 0; resizeAttempt < 8; resizeAttempt++) {
            BufferedImage jpegImage = renderRgb(source, width, height);
            for (float quality : qualities) {
                byte[] encoded = encodeJpeg(jpegImage, quality);
                if (encoded.length <= MAX_IMAGE_BYTES) {
                    return encoded;
                }
            }

            width = Math.max(64, Math.round(width * 0.78F));
            height = Math.max(64, Math.round(height * 0.78F));
        }

        throw new IOException(
                "Painting image remains larger than MineAstr's 768 KiB limit after compression");
    }

    private static BufferedImage renderRgb(BufferedImage source, int width, int height) {
        BufferedImage target = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = target.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(0, 0, width, height);
            graphics.setRenderingHint(
                    RenderingHints.KEY_INTERPOLATION,
                    RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            graphics.setRenderingHint(
                    RenderingHints.KEY_RENDERING,
                    RenderingHints.VALUE_RENDER_QUALITY);
            graphics.drawImage(source, 0, 0, width, height, null);
        } finally {
            graphics.dispose();
        }
        return target;
    }

    private static byte[] encodeJpeg(BufferedImage image, float quality) throws IOException {
        ImageWriter writer = ImageIO.getImageWritersByFormatName("jpeg")
                .next();
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             MemoryCacheImageOutputStream output = new MemoryCacheImageOutputStream(bytes)) {
            writer.setOutput(output);
            ImageWriteParam parameters = writer.getDefaultWriteParam();
            if (parameters.canWriteCompressed()) {
                parameters.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
                parameters.setCompressionQuality(quality);
            }
            writer.write(null, new IIOImage(image, null, null), parameters);
            output.flush();
            return bytes.toByteArray();
        } finally {
            writer.dispose();
        }
    }

    public static String selectTranslation(Map<?, ?> translations, String language) {
        for (Map.Entry<?, ?> entry : translations.entrySet()) {
            if (!normalizeLanguage(stringValue(entry.getKey())).equals(language)) {
                continue;
            }
            String value = stringValue(entry.getValue()).strip();
            if (!value.isBlank()) {
                return value;
            }
        }

        int separator = language.indexOf('_');
        String family = separator < 0 ? language : language.substring(0, separator);
        for (Map.Entry<?, ?> entry : translations.entrySet()) {
            String candidate = normalizeLanguage(stringValue(entry.getKey()));
            String value = stringValue(entry.getValue()).strip();
            if (!value.isBlank()
                    && (candidate.equals(family) || candidate.startsWith(family + "_"))) {
                return value;
            }
        }
        return "";
    }

    public static String normalizeLanguage(String language) {
        return language == null
                ? ""
                : language.strip().replace('-', '_').toLowerCase(Locale.ROOT);
    }

    private static String stringValue(Object value) {
        return value == null ? "" : value.toString();
    }
}
