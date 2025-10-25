'use client';

import { useEffect, useState } from "react";
import { useUserStore } from "@/store/userStore";
import { UserAPI, BodyUpdateProfile, UserProfile } from "@/lib/api"; 
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useRouter } from "next/navigation";

const api = new UserAPI();

export default function ProfilePage() {
  const router = useRouter();
  const user = useUserStore((state) => state.user);
  const setUser = useUserStore((state) => state.setUser);

  const [form, setForm] = useState<BodyUpdateProfile>({
    user_login: user?.user_login || "",
    user_full_name: user?.user_full_name || "",
    user_email: user?.user_email || "",
    photo: null,
  });

  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      router.replace("/login");
    }
  }, [user, router]);

  if (!user) return null;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, files } = e.target;
    if (name === "photo" && files) setForm({ ...form, photo: files[0] });
    else setForm({ ...form, [name]: value });
  };

  const handleUpdate = async () => {
    setLoading(true);
    try {
      const updatedUser: UserProfile = await api.updateProfile(form);
      setUser(updatedUser);
      alert("Профиль обновлен");
    } catch (err) {
      console.error(err);
      alert("Ошибка обновления");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="p-6 max-w-md mx-auto mt-10">
      <h1 className="text-xl font-bold mb-4">Профиль</h1>
      <Input
        name="user_login"
        placeholder="Логин"
        value={form.user_login || ""}
        onChange={handleChange}
        className="mb-2"
      />
      <Input
        name="user_full_name"
        placeholder="Полное имя"
        value={form.user_full_name || ""}
        onChange={handleChange}
        className="mb-2"
      />
      <Input
        name="user_email"
        placeholder="Email"
        value={form.user_email || ""}
        onChange={handleChange}
        className="mb-2"
      />
      <Input
        type="file"
        name="photo"
        onChange={handleChange}
        className="mb-4"
      />
      <Button onClick={handleUpdate} disabled={loading} className="w-full">
        {loading ? "Сохраняем..." : "Сохранить"}
      </Button>
    </Card>
  );
}
