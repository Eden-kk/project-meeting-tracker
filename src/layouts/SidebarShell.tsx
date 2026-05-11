import { Outlet } from 'react-router-dom';
import { MobileSidebar, Sidebar } from '../components/Sidebar';
import { SearchBar } from '../components/SearchBar';

export function SidebarShell() {
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <MobileSidebar />
      <div className="flex">
        <Sidebar />
        <main className="min-w-0 flex-1 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="mb-4 hidden justify-end md:flex">
              <SearchBar />
            </div>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
