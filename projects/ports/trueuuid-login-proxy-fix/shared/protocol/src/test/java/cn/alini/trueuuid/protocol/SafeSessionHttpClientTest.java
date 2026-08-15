package cn.alini.trueuuid.protocol;

import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeSessionHttpClientTest {
    private static final URI MOJANG_HAS_JOINED = URI.create(
            "https://sessionserver.mojang.com/session/minecraft/hasJoined?username=Player&serverId=nonce");

    @Test
    void allowsFlClashSyntheticDnsOnlyForFixedMojangHasJoinedEndpoint() throws Exception {
        assertTrue(SafeSessionHttpClient.isTrustedAddress(
                MOJANG_HAS_JOINED, InetAddress.getByName("198.18.0.1")));
        assertTrue(SafeSessionHttpClient.isTrustedAddress(
                MOJANG_HAS_JOINED, InetAddress.getByName("198.19.255.254")));

        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                URI.create("https://auth.example.com/sessionserver/session/minecraft/hasJoined"),
                InetAddress.getByName("198.18.0.1")));
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                URI.create("https://sessionserver.mojang.com/other"),
                InetAddress.getByName("198.18.0.1")));
    }

    @Test
    void stillRejectsPrivateAndBenchmarkAdjacentAddresses() throws Exception {
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                MOJANG_HAS_JOINED, InetAddress.getByName("10.0.0.1")));
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                MOJANG_HAS_JOINED, InetAddress.getByName("198.51.100.1")));
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                MOJANG_HAS_JOINED, InetAddress.getByName("203.0.113.1")));
    }

    @Test
    void doesNotBroadenSyntheticAllowanceToMojangVariants() throws Exception {
        InetAddress synthetic = InetAddress.getByName("198.18.1.1");
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                URI.create("http://sessionserver.mojang.com/session/minecraft/hasJoined"), synthetic));
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                URI.create("https://sessionserver.mojang.com:444/session/minecraft/hasJoined"), synthetic));
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                URI.create("https://sessionserver.mojang.com/session/minecraft/hasJoined/"), synthetic));
        assertFalse(SafeSessionHttpClient.isTrustedAddress(
                URI.create("https://sessionserver.mojang.com/session/minecraft/hasJoined#fragment"), synthetic));
    }
}
