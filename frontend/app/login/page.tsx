'use client';

import { useState } from "react";
import { useRouter } from "next/navigation";
import { UserAPI, UserLogin, UserCreate } from "@/lib/api";
import { useUserStore } from "@/store/userStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const api = new UserAPI();

export default function AuthPage() {
  const router = useRouter();
  const setUser = useUserStore((state) => state.setUser);

  const [mode, setMode] = useState<"login" | "register" | "verify">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [loginData, setLoginData] = useState<UserLogin>({
    user_indificator: "",
    user_password: "",
  });

  const [registerData, setRegisterData] = useState<UserCreate>({
    user_login: "",
    user_full_name: "",
    user_email: "",
    user_password: "",
  });

  const [token, setToken] = useState("");

  // --- Handlers ---
  const handleChangeLogin = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLoginData({ ...loginData, [e.target.name]: e.target.value });
  };

  const handleChangeRegister = (e: React.ChangeEvent<HTMLInputElement>) => {
    setRegisterData({ ...registerData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      if (mode === "login") {
        const user = await api.login(loginData);
        setUser(user);
        router.push("/a/profile");
      } 
      else if (mode === "register") {
        await api.register(registerData);
        setSuccess("Регистрация успешна! Проверьте почту и введите токен для подтверждения.");
        setMode("verify");
      } 
      else if (mode === "verify") {
        await api.verifyEmail(token);
        setSuccess("Почта успешно подтверждена! Авторизация...");
        await new Promise((r) => setTimeout(r, 1000));
        const user = await api.login({
          user_indificator: registerData.user_email,
          user_password: registerData.user_password,
        });
        setUser(user);
        router.push("/a/profile");
      }
    } catch (err: any) {
      setError(err?.response?.data?.message || "Ошибка при выполнении запроса");
    } finally {
      setLoading(false);
    }
  };

  // --- UI ---
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50 px-4">
      <Card className="w-full max-w-md shadow-lg border border-gray-200 rounded-2xl">
        <CardHeader>
          <CardTitle className="text-center text-2xl font-semibold">
            {mode === "login" && "Вход в аккаунт"}
            {mode === "register" && "Регистрация"}
            {mode === "verify" && "Подтверждение почты"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-3">
            {error && <p className="text-red-500 text-sm">{error}</p>}
            {success && <p className="text-green-600 text-sm">{success}</p>}

            {mode === "login" && (
              <>
                <Input
                  name="user_indificator"
                  placeholder="Логин или Email"
                  value={loginData.user_indificator}
                  onChange={handleChangeLogin}
                  disabled={loading}
                />
                <Input
                  name="user_password"
                  type="password"
                  placeholder="Пароль"
                  value={loginData.user_password}
                  onChange={handleChangeLogin}
                  disabled={loading}
                />
              </>
            )}

            {mode === "register" && (
              <>
                <Input
                  name="user_login"
                  placeholder="Логин"
                  value={registerData.user_login}
                  onChange={handleChangeRegister}
                  disabled={loading}
                />
                <Input
                  name="user_full_name"
                  placeholder="Полное имя"
                  value={registerData.user_full_name}
                  onChange={handleChangeRegister}
                  disabled={loading}
                />
                <Input
                  name="user_email"
                  placeholder="Email"
                  type="email"
                  value={registerData.user_email}
                  onChange={handleChangeRegister}
                  disabled={loading}
                />
                <Input
                  name="user_password"
                  type="password"
                  placeholder="Пароль"
                  value={registerData.user_password}
                  onChange={handleChangeRegister}
                  disabled={loading}
                />
              </>
            )}

            {mode === "verify" && (
              <>
                <p className="text-sm text-gray-600">
                  Введите токен, который вы получили по почте.
                </p>
                <Input
                  placeholder="Введите токен"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  disabled={loading}
                />
              </>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={loading}
            >
              {loading
                ? "Загрузка..."
                : mode === "login"
                ? "Войти"
                : mode === "register"
                ? "Зарегистрироваться"
                : "Подтвердить"}
            </Button>
          </form>

          {/* --- Переключение между режимами --- */}
          {mode !== "verify" && (
            <div className="text-center mt-4 text-sm text-gray-600">
              {mode === "login" ? (
                <>
                  Нет аккаунта?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setMode("register");
                      setError("");
                      setSuccess("");
                    }}
                    className="text-blue-600 hover:underline"
                  >
                    Зарегистрироваться
                  </button>
                </>
              ) : (
                <>
                  Уже есть аккаунт?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setMode("login");
                      setError("");
                      setSuccess("");
                    }}
                    className="text-blue-600 hover:underline"
                  >
                    Войти
                  </button>
                </>
              )}
            </div>
          )}

          {/* --- Повторная отправка письма --- */}
          {mode === "verify" && (
            <div className="text-center mt-4 text-sm text-gray-500">
              <button
                type="button"
                onClick={async () => {
                  try {
                    await api.resendVerification();
                    setSuccess("Письмо с подтверждением отправлено повторно.");
                  } catch {
                    setError("Не удалось отправить письмо.");
                  }
                }}
                className="text-blue-600 hover:underline"
              >
                Отправить токен повторно
              </button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
