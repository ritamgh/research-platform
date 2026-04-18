import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface AnswerCardProps {
  answer: string
}

export function AnswerCard({ answer }: AnswerCardProps) {
  return (
    <div className="answer-section">
      <div className="section-label">ANSWER</div>
      <div className="answer-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
      </div>
    </div>
  )
}
