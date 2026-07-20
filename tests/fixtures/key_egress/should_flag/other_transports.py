# The old linter knew only about urllib. Every one of these reaches the wire
# with credentials attached and was completely invisible to it.
import http.client
import socket

import httpx
import requests


def via_http_client(host: str, key: str):
    c = http.client.HTTPSConnection(host)
    c.request("GET", "/v1/models", headers={"Authorization": f"Bearer {key}"})
    return c.getresponse()


def via_socket(host: str, key: str):
    s = socket.create_connection((host, 443))
    s.sendall(f"GET / HTTP/1.1\r\nAuthorization: Bearer {key}\r\n\r\n".encode())
    return s


def via_requests(url: str, key: str):
    return requests.get(url, headers={"Authorization": f"Bearer {key}"})


def via_httpx(url: str, key: str):
    return httpx.get(url, headers={"Authorization": f"Bearer {key}"})
