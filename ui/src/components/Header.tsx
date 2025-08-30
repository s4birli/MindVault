'use client';

import React, { useState } from 'react';
import { SearchIcon, SettingsIcon, UserIcon, MenuIcon, XIcon } from 'lucide-react';

interface HeaderProps {
    currentThreadTitle?: string;
    onSearch?: (query: string) => void;
    onToggleSidebar?: () => void;
    isSidebarOpen?: boolean;
}

export default function Header({
    currentThreadTitle,
    onSearch,
    onToggleSidebar,
    isSidebarOpen = true
}: HeaderProps) {
    const [searchQuery, setSearchQuery] = useState('');
    const [showProfileMenu, setShowProfileMenu] = useState(false);

    const handleSearchSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (searchQuery.trim() && onSearch) {
            onSearch(searchQuery.trim());
        }
    };

    return (
        <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
            {/* Left Side - Logo and Navigation */}
            <div className="flex items-center gap-4">
                {/* Mobile Menu Toggle */}
                <button
                    onClick={onToggleSidebar}
                    className="lg:hidden p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    {isSidebarOpen ? <XIcon size={20} /> : <MenuIcon size={20} />}
                </button>

                {/* Logo and App Name */}
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                        <span className="text-white font-bold text-sm">MV</span>
                    </div>
                    <div className="hidden sm:block">
                        <h1 className="text-xl font-bold text-gray-900">MindVault</h1>
                        <p className="text-xs text-gray-500">AI Assistant</p>
                    </div>
                </div>

                {/* Current Thread Title (Mobile) */}
                {currentThreadTitle && (
                    <div className="sm:hidden">
                        <p className="text-sm font-medium text-gray-700 truncate max-w-32">
                            {currentThreadTitle}
                        </p>
                    </div>
                )}
            </div>

            {/* Center - Search (Desktop) */}
            <div className="hidden md:block flex-1 max-w-md mx-4">
                <form onSubmit={handleSearchSubmit} className="relative">
                    <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search in current thread..."
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                    />
                </form>
            </div>

            {/* Right Side - Profile and Settings */}
            <div className="flex items-center gap-2">
                {/* Search (Mobile) */}
                <div className="md:hidden">
                    <form onSubmit={handleSearchSubmit} className="relative">
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="Search..."
                            className="w-32 pl-8 pr-2 py-1.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                        />
                        <SearchIcon className="absolute left-2 top-1/2 transform -translate-y-1/2 text-gray-400" size={14} />
                    </form>
                </div>

                {/* Settings Button */}
                <button className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
                    <SettingsIcon size={20} />
                </button>

                {/* Profile Menu */}
                <div className="relative">
                    <button
                        onClick={() => setShowProfileMenu(!showProfileMenu)}
                        className="flex items-center gap-2 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <div className="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center">
                            <UserIcon size={16} />
                        </div>
                        <span className="hidden sm:block text-sm font-medium">Guest</span>
                    </button>

                    {/* Profile Dropdown */}
                    {showProfileMenu && (
                        <div className="absolute right-0 top-full mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg py-2 z-50">
                            <div className="px-4 py-2 border-b border-gray-100">
                                <p className="text-sm font-medium text-gray-900">Guest User</p>
                                <p className="text-xs text-gray-500">No account connected</p>
                            </div>
                            <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors">
                                Settings
                            </button>
                            <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors">
                                Help & Support
                            </button>
                            <div className="border-t border-gray-100 mt-2 pt-2">
                                <button className="w-full text-left px-4 py-2 text-sm text-blue-600 hover:bg-gray-50 transition-colors">
                                    Sign In (Coming Soon)
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Click outside to close profile menu */}
            {showProfileMenu && (
                <div
                    className="fixed inset-0 z-40"
                    onClick={() => setShowProfileMenu(false)}
                />
            )}
        </header>
    );
}
