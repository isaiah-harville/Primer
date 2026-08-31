<script lang="ts">
	import AuthModeWarning from '$lib/components/AuthModeWarning.svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();
</script>

<AuthModeWarning authEnabled={data.capabilities.auth_enabled} />

<!--
  A skip link first, because the navigation is on every page and a keyboard
  user should not have to tab through it to reach the content each time.
-->
<a class="skip" href="#main">Skip to content</a>

<header>
	<a class="brand" href="/libraries">Primer</a>
	<nav aria-label="Main">
		<a href="/libraries">Libraries</a>
		{#if data.capabilities.chat_available}
			<a href="/chat">Chat</a>
		{/if}
	</nav>
</header>

<main id="main">
	{@render children()}
</main>

<style>
	:global(body) {
		margin: 0;
		font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
		color: #0f172a;
	}
	.skip {
		position: absolute;
		left: -9999px;
	}
	.skip:focus {
		left: 0.5rem;
		top: 0.5rem;
		background: #fff;
		padding: 0.5rem 0.75rem;
		z-index: 10;
	}
	header {
		display: flex;
		align-items: baseline;
		gap: 1.5rem;
		padding: 0.875rem 1.25rem;
		border-bottom: 1px solid #e2e8f0;
	}
	.brand {
		font-weight: 700;
		font-size: 1.125rem;
		text-decoration: none;
		color: inherit;
	}
	nav {
		display: flex;
		gap: 1rem;
	}
	main {
		max-width: 60rem;
		margin: 0 auto;
		padding: 1.5rem 1.25rem 4rem;
	}
</style>
