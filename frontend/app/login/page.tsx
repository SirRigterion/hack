'use client';

import { useState } from "react";
import { useRouter } from "next/navigation";
import { UserAPI, UserLogin } from "@/lib/api";
import { useUserStore } from "@/store/userStore";
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input";

const api = new UserAPI();

export default function LoginPage() {
  const router = useRouter();
  const setUser = useUserStore((state) => state.setUser);

  const [loginData, setLoginData] = useState<UserLogin>({
    user_indificator: "",
    user_password: "",
  });

  const [error, setError] = useState("");

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLoginData({ ...loginData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const user = await api.login(loginData);
      setUser(user);
      router.push("/profile"); // редирект после логина
    } catch (err: any) {
      setError(err?.response?.data?.message || "Ошибка при входе");
    }
  };

  return (
    <div className="flex items-center justify-center h-screen">
      <form onSubmit={handleSubmit} className="w-96 p-6 bg-white shadow rounded">
        <h1 className="text-2xl font-bold mb-4">Вход</h1>
        {error && <p className="text-red-500 mb-2">{error}</p>}
        <Input
          name="user_indificator"
          placeholder="Логин или Email"
          value={loginData.user_indificator}
          onChange={handleChange}
          className="mb-2"
        />
        <Input
          name="user_password"
          type="password"
          placeholder="Пароль"
          value={loginData.user_password}
          onChange={handleChange}
          className="mb-4"
        />
        <Button type="submit" className="w-full">Войти</Button>
      </form>
    </div>
  );
}
