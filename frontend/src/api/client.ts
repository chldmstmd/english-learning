import ky from "ky";

const BASE = "http://localhost:8000";

export const api = ky.create({
  prefixUrl: `${BASE}/api/v1`,
  timeout: 15000,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = localStorage.getItem("auth_token");
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
      },
    ],
    afterResponse: [
      (_request, _options, response) => {
        if (response.status === 401) {
          localStorage.removeItem("auth_token");
          localStorage.removeItem("auth_user");
          window.location.href = "/login";
        }
        return response;
      },
    ],
  },
});

// Unauthenticated client for auth endpoints
export const authApi = ky.create({
  prefixUrl: `${BASE}/auth`,
  timeout: 10000,
});
