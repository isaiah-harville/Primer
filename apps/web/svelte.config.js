import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
export default {
	preprocess: vitePreprocess(),
	kit: {
		// Node rather than a static build: the browser never talks to Control
		// directly. Requests go through this server, which is what lets the
		// deployment keep Control unreachable from outside the cluster.
		adapter: adapter(),
	},
};
