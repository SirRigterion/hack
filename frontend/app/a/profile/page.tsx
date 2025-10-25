'use client';

import { useEffect, useState } from "react";
import { useUserStore } from "@/store/userStore";
import { UserAPI, BodyUpdateProfile, UserProfile } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent, CardTitle } from "@/components/ui/card";
import { useRouter } from "next/navigation";
// import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";

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
  const [preview, setPreview] = useState<string | null>(user?.user_avatar_url || null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) router.replace("/login");
  }, [user, router]);

  if (!user) return null;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, files } = e.target;
    if (name === "photo" && files) {
      setForm({ ...form, photo: files[0] });
      setPreview(URL.createObjectURL(files[0]));
    } else {
      setForm({ ...form, [name]: value });
    }
  };

  const handleUpdate = async () => {
    setLoading(true);
    try {
      const updatedUser: UserProfile = await api.updateProfile(form);
      setUser(updatedUser);
      alert("✅ Профиль успешно обновлён");
    } catch (err) {
      console.error(err);
      alert("❌ Ошибка при обновлении");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="max-w-lg mx-auto p-6 shadow-lg rounded-2xl border border-gray-200">
      <CardHeader>
        <CardTitle className="text-center text-2xl font-semibold">
          👤 Мой профиль
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col items-center mb-4">
          {/* <Avatar className="w-24 h-24 mb-2 border-2 border-gray-300">
            <AvatarImage src={preview || ""} />
            <AvatarFallback>
              {user.user_full_name?.[0]?.toUpperCase() || "U"}
            </AvatarFallback>
          </Avatar> */}
          <Input
            type="file"
            name="photo"
            accept="image/*"
            onChange={handleChange}
            className="max-w-xs text-sm"
          />
        </div>

        <Input
          name="user_login"
          placeholder="Логин"
          value={form.user_login || ""}
          onChange={handleChange}
        />
        <Input
          name="user_full_name"
          placeholder="Полное имя"
          value={form.user_full_name || ""}
          onChange={handleChange}
        />
        <Input
          name="user_email"
          placeholder="Email"
          value={form.user_email || ""}
          onChange={handleChange}
        />

        <Button onClick={handleUpdate} disabled={loading} className="w-full">
          {loading ? "Сохраняем..." : "Сохранить изменения"}
        </Button>
      </CardContent>
    </Card>
  );
}
