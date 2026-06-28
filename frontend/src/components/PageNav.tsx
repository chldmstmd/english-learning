import { useState, useRef, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Settings, LogOut } from "lucide-react";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";
import type { AppSettings } from "../types";

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (val: boolean) => void;
}) {
  return (
    <div
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative w-10 h-5 rounded-full cursor-pointer transition-colors shrink-0 ${
        checked ? "bg-blue-500" : "bg-gray-200"
      }`}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </div>
  );
}

export function PageNav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  function handleLogout() {
    logout();
    queryClient.clear();
    navigate("/login");
  }

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get("settings").json<AppSettings>(),
  });

  const settingsMutation = useMutation({
    mutationFn: (body: Partial<AppSettings>) =>
      api.patch("settings", { json: body }).json<AppSettings>(),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
    },
  });

  // Close panel when clicking outside
  useEffect(() => {
    if (!settingsOpen) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [settingsOpen]);

  return (
    <div className="border-b border-gray-100">
      <div className="max-w-3xl mx-auto px-6">
        <div className="flex items-center justify-between h-12">
          <div className="flex gap-1">
            <Link
              to="/"
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                pathname === "/"
                  ? "bg-gray-100 text-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              文本
            </Link>
          </div>

          <div className="flex items-center gap-2">
            {user && (
              <span className="text-xs text-gray-400 hidden sm:block truncate max-w-[140px]">
                {user.email}
              </span>
            )}
            <button
              type="button"
              onClick={handleLogout}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1"
              aria-label="退出登录"
              title="退出登录"
            >
              <LogOut size={15} />
            </button>

          <div className="relative" ref={panelRef}>
            <button
              type="button"
              onClick={() => setSettingsOpen((v) => !v)}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1"
              aria-label="设置"
            >
              <Settings size={16} />
            </button>

            {settingsOpen && (
              <div className="absolute right-0 top-8 w-64 bg-white border border-gray-200 rounded-lg shadow-lg p-4 z-50">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
                  翻译设置
                </p>

                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-gray-700">启用免费翻译降级</span>
                  <Toggle
                    checked={settings?.use_free_translation_fallback ?? true}
                    onChange={(val) =>
                      settingsMutation.mutate({ use_free_translation_fallback: val })
                    }
                  />
                </div>
                <p className="text-xs text-gray-400 mt-1.5 mb-3">
                  关闭后，AI不可用时翻译会直接失败
                </p>

                <div className="border-t border-gray-100 pt-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-gray-700">翻译完成后打开侧栏</span>
                    <Toggle
                      checked={settings?.auto_open_sidebar_on_mark ?? true}
                      onChange={(val) =>
                        settingsMutation.mutate({ auto_open_sidebar_on_mark: val })
                      }
                    />
                  </div>
                  <p className="text-xs text-gray-400 mt-1.5">
                    关闭后，只在原文上方显示译文
                  </p>
                </div>
              </div>
            )}
          </div>
          </div>
        </div>
      </div>
    </div>
  );
}
