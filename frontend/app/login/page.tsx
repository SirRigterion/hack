export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
      <div className="bg-white/10 backdrop-blur-md rounded-2xl p-8 w-[380px]">
        <h1 className="text-2xl font-semibold mb-4 text-center">Вход / Регистрация</h1>
        <form className="flex flex-col gap-4">
          <input type="text" placeholder="Email" className="px-3 py-2 rounded bg-zinc-800 border border-zinc-700" />
          <input type="password" placeholder="Пароль" className="px-3 py-2 rounded bg-zinc-800 border border-zinc-700" />
          <button className="bg-blue-600 hover:bg-blue-700 rounded py-2 transition">Войти</button>
        </form>
      </div>
    </main>
  );
}
