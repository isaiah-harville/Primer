import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/svelte';
import { afterEach } from 'vitest';

// Without this each test leaves its component mounted, and queries start
// matching elements from a previous test rather than this one.
afterEach(cleanup);
