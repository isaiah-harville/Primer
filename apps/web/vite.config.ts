import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	// Only under Vitest, and only there: without the browser condition Svelte
	// resolves to its server build, where mounting a component does not
	// exist. Applying it unconditionally would break server-side rendering.
	resolve: process.env.VITEST ? { conditions: ['browser'] } : undefined,
	test: {
		environment: 'jsdom',
		include: ['src/**/*.test.ts'],
		setupFiles: ['./vitest-setup.ts'],
	},
});
