export default function ProfilePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
      <div className="bg-white/10 backdrop-blur-md rounded-2xl p-8 w-[400px] text-center">
        <h1 className="text-2xl font-semibold mb-2">Профиль</h1>
        <p className="text-zinc-400 mb-4">Имя пользователя: <span className="text-white font-medium">demo_user</span></p>
        <button className="bg-blue-600 hover:bg-blue-700 rounded py-2 px-4 transition">Перейти к звонку</button>
      </div>
    </main>
  );
}
