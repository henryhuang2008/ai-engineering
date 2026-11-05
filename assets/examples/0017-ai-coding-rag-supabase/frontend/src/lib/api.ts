import { http } from '@/lib/http'

export { ApiError } from '@/lib/http'

export interface ChatThread {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  citations: ChatCitation[]
}

export interface ChatCitation {
  citation_index: number
  chunk_id: string
  quote: string | null
  ticker: string
  company_name: string
  filing_type: string
  filing_date: string
  fiscal_year: number
  accession_number: string
  source_url: string
  section: string | null
  page_references: number[]
  passage: string
}

export interface ChatThreadHistory extends ChatThread {
  messages: ChatMessage[]
}

export const api = {
  ...http,
  createThread: (title = 'New chat') =>
    http.post<ChatThread>('/chat/threads', { title }),
  listThreads: () => http.get<ChatThread[]>('/chat/threads'),
  getThread: (threadId: string) =>
    http.get<ChatThreadHistory>(`/chat/threads/${encodeURIComponent(threadId)}`),
}
