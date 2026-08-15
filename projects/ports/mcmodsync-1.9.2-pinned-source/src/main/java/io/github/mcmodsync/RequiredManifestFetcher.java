package io.github.mcmodsync;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.function.Consumer;

final class RequiredManifestFetcher {
    private static final int ATTEMPTS = 3;

    private RequiredManifestFetcher() {
    }

    static HttpClient createClient(Duration connectTimeout) {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(connectTimeout)
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    static byte[] fetch(
            HttpClient client,
            URI uri,
            Duration requestTimeout,
            long maximumBytes,
            String userAgent,
            String description,
            Consumer<String> logger) throws IOException, InterruptedException {
        boolean english = description.codePoints().noneMatch(codePoint ->
                Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN);
        IOException lastFailure = null;
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .version(HttpClient.Version.HTTP_1_1)
                        .timeout(requestTimeout)
                        .header("User-Agent", userAgent)
                        .GET()
                        .build();
                HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
                if (response.statusCode() != 200) {
                    closeQuietly(response.body());
                    throw new IOException(description
                            + (english ? " server returned HTTP " : "服务器返回 HTTP ")
                            + response.statusCode());
                }
                try (InputStream input = response.body()) {
                    return readLimited(input, maximumBytes, description);
                }
            } catch (IOException failure) {
                lastFailure = failure;
                if (attempt == ATTEMPTS) {
                    break;
                }
                logger.accept(english
                        ? description + " read failed (attempt " + attempt + "/" + ATTEMPTS + "): "
                                + failure.getMessage() + "; retrying automatically…"
                        : description + "读取失败（第 " + attempt + "/" + ATTEMPTS
                                + " 次）：" + failure.getMessage() + "；正在自动重试……");
                Thread.sleep(400L * attempt);
            }
        }
        throw lastFailure == null
                ? new IOException(description + (english ? " read failed" : "读取失败"))
                : lastFailure;
    }

    private static byte[] readLimited(InputStream input, long maximumBytes, String description) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        long total = 0;
        int read;
        while ((read = input.read(buffer)) >= 0) {
            total += read;
            if (total > maximumBytes) {
                boolean english = description.codePoints().noneMatch(codePoint ->
                        Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN);
                throw new IOException(description + (english ? " exceeds the size limit" : "超过大小限制"));
            }
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
    }

    private static void closeQuietly(InputStream input) {
        if (input == null) {
            return;
        }
        try {
            input.close();
        } catch (IOException ignored) {
        }
    }
}
