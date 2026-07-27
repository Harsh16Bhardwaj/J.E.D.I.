import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/top-bar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r-2 border-foreground lg:block">
        <Sidebar />
      </aside>
      <div className="lg:pl-72">
        <TopBar />
        <main className="min-h-[calc(100vh-4rem)] overflow-hidden px-4 py-8 sm:px-6 lg:px-10 lg:py-12">
          {children}
        </main>
      </div>
    </div>
  );
}
