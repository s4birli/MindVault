# MindVault UI

A modern, responsive ChatGPT-like interface for the MindVault AI assistant built with Next.js 15, TypeScript, and Tailwind CSS.

## Features

- 🧵 **Thread Management**: Create, edit, and organize chat threads like ChatGPT
- 💬 **Real-time Chat**: Interactive chat interface with message history
- 📎 **Multimodal Support**: Upload and handle text, images, audio, and documents
- 📱 **Responsive Design**: Works seamlessly on desktop, tablet, and mobile
- 🔄 **Auto-generated Titles**: Thread titles are automatically generated from first message
- 💾 **Local Storage**: Conversations persist in browser storage
- 🎨 **Modern UI**: Clean, intuitive interface with smooth animations
- 🔌 **Backend Integration**: Connects to FastAPI backend with both Ask and Agent APIs

## Tech Stack

- **Framework**: Next.js 15 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **HTTP Client**: Axios
- **Markdown**: React Markdown
- **Date Handling**: date-fns
- **ID Generation**: UUID

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn
- MindVault backend running on port 8000

### Installation

1. Install dependencies:
```bash
npm install
```

2. Set up environment variables:
```bash
# Create .env.local file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

3. Run the development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000) in your browser

### Docker Setup

Build and run with Docker:

```bash
# Build the Docker image
docker build -t mindvault-ui .

# Run the container
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:8000 mindvault-ui
```

Or use with docker-compose from the main project:

```bash
# From the main MindVault directory
docker-compose -f docker-compose.dev.yml up frontend
```

## Project Structure

```
src/
├── app/                    # Next.js App Router
│   ├── globals.css        # Global styles
│   ├── layout.tsx         # Root layout
│   └── page.tsx          # Home page
├── components/            # React components
│   ├── ChatArea.tsx      # Main chat interface
│   ├── ChatLayout.tsx    # Overall layout
│   ├── Message.tsx       # Individual message component
│   ├── MessageInput.tsx  # Message input with attachments
│   └── Sidebar.tsx       # Thread sidebar
├── lib/                  # Utilities
│   ├── api.ts           # API client
│   └── storage.ts       # Local storage utilities
└── types/               # TypeScript definitions
    └── index.ts        # Type definitions
```

## Features Overview

### Thread Management
- Create new chat threads
- Auto-generate thread titles from first message
- Edit thread titles inline
- Delete threads
- Persistent storage in localStorage

### Chat Interface
- Send text messages
- Upload multiple file types (images, audio, documents)
- View message history
- Loading states and error handling
- Markdown rendering for assistant responses
- Source citations with links

### Multimodal Support
- **Images**: Preview uploaded images inline
- **Audio**: Play audio files with native controls
- **Documents**: Support for PDF, DOC, TXT, and more
- **File Size Limits**: 10MB maximum per file
- **Multiple Files**: Upload multiple files per message

### Responsive Design
- Mobile-first approach
- Collapsible sidebars
- Touch-friendly interactions
- Optimized for all screen sizes

## API Integration

The UI connects to two main backend endpoints:

### Ask API (`/ask`)
- General question answering
- Document retrieval and summarization
- Source citations

### Agent API (`/agent/act`)
- Intent-based actions
- Search and find operations
- Local document processing

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint

### Code Style

- TypeScript with strict mode
- ESLint configuration included
- Tailwind CSS for styling
- Component-based architecture

## Deployment

### Production Build

```bash
npm run build
npm start
```

### Docker Production

```bash
docker build -t mindvault-ui .
docker run -p 3000:3000 mindvault-ui
```

## Future Enhancements

- 📅 **Calendar Integration**: Left sidebar for appointments
- ✅ **Todo List**: Right sidebar for task management  
- 🔐 **Authentication**: User login and session management
- 🌙 **Dark Mode**: Theme switching
- 🔊 **Voice Input**: Speech-to-text functionality
- 💾 **Cloud Sync**: Sync conversations across devices

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is part of the MindVault system.