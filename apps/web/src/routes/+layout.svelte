<script lang="ts">
	import '../app.css';
	import AuthModeWarning from '$lib/components/AuthModeWarning.svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();
</script>

<AuthModeWarning authEnabled={data.capabilities.auth_enabled} />

<!--
  A skip link first, because the navigation is on every page and a keyboard
  user should not have to tab through it to reach the content each time.
-->
<a
	href="#main"
	class="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50
		focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:shadow"
>
	Skip to content
</a>

<header class="flex items-baseline gap-6 border-b border-border px-5 py-3.5">
	<a href="/libraries" class="text-lg font-bold">Primer</a>
	<nav aria-label="Main" class="flex gap-4 text-sm">
		<a href="/libraries" class="hover:underline">Libraries</a>
		{#if data.capabilities.chat_available}
			<a href="/chat" class="hover:underline">Chat</a>
		{/if}
	</nav>
</header>

<main id="main" class="mx-auto max-w-4xl px-5 pb-16 pt-6">
	{@render children()}
</main>
