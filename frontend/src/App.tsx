import { lazy, Suspense, useEffect, useState } from 'react';
import { LabPage } from './features/lab/LabPage';

const LearningFlow = lazy(() => import('./features/learning/LearningFlow').then((module) => ({ default: module.LearningFlow })));

export function App() {
  const [learning, setLearning] = useState(() => window.location.hash === '#learn');
  useEffect(() => {
    const navigate = () => setLearning(window.location.hash === '#learn');
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  if (!learning) return <LabPage />;
  return <Suspense fallback={<main className="page" role="status">正在加载引导学习…</main>}><LearningFlow /></Suspense>;
}
