import { lazy, Suspense, useEffect, useState } from 'react';
import { LabPage } from './features/lab/LabPage';

const LearningFlow = lazy(() => import('./features/learning/LearningFlow').then((module) => ({ default: module.LearningFlow })));

export function App() {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const navigate = () => setHash(window.location.hash);
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  if (hash !== '#learn' && !hash.startsWith('#learn?')) return <LabPage />;
  const studySessionId = new URLSearchParams(hash.slice('#learn'.length)).get('study') ?? undefined;
  return <Suspense fallback={<main className="page" role="status">正在加载引导学习…</main>}>
    <LearningFlow key={studySessionId ?? 'practice'} studySessionId={studySessionId} />
  </Suspense>;
}
