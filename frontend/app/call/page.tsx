export default function CallPage() {
  return (
    <main className="flex min-h-screen bg-zinc-950 text-white">
      {/* Видео-зона */}
      <section className="flex-1 flex items-center justify-center bg-zinc-900/40">
        <div className="w-[80%] h-[80%] bg-black/40 rounded-2xl flex items-center justify-center text-zinc-500">
          Видео-зона (заглушка)
        </div>
      </section>

      {/* Чат-зона */}
      <aside className="w-[320px] bg-white/10 backdrop-blur-md flex flex-col">
        <header className="p-4 border-b border-zinc-800 text-lg font-medium">Чат</header>
        <div className="flex-1 p-4 overflow-y-auto text-zinc-400">Нет сообщений</div>
        <footer className="p-4 border-t border-zinc-800">
          <input
            type="text"
            placeholder="Введите сообщение..."
            className="w-full px-3 py-2 rounded bg-zinc-800 border border-zinc-700"
          />
        </footer>
      </aside>
    </main>
  );
}
