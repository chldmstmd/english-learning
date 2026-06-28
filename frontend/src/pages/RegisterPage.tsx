import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/client";
import { useAuthStore } from "../store/authStore";
import type { AuthUser, TokenResponse } from "../types";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("密码至少 6 位");
      return;
    }
    setLoading(true);
    try {
      const data = await authApi
        .post("register", { json: { email, password } })
        .json<TokenResponse>();

      const me = await authApi
        .get("me", { headers: { Authorization: `Bearer ${data.access_token}` } })
        .json<AuthUser>();

      setAuth(data.access_token, me);
      navigate("/");
    } catch (err: unknown) {
      const msg = (err as { response?: Response })?.response;
      if (msg?.status === 409) {
        setError("该邮箱已被注册");
      } else {
        setError("注册失败，请重试");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-1">注册</h1>
        <p className="text-sm text-gray-400 mb-6">Context Translation Layer</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="至少 6 位"
            />
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-500 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            {loading ? "注册中..." : "创建账号"}
          </button>
        </form>

        <p className="text-sm text-gray-400 text-center mt-6">
          已有账号？{" "}
          <Link to="/login" className="text-blue-500 hover:underline">
            登录
          </Link>
        </p>
      </div>
    </div>
  );
}
