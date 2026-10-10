import { createRoot } from 'react-dom/client';
import { App } from './App';
import { SlipProvider } from './state';
import './styles/app.css';

const el = document.getElementById('root');
if (el) {
  createRoot(el).render(
    <SlipProvider>
      <App />
    </SlipProvider>,
  );
}
