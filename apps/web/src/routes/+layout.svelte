<script lang="ts">
	import { Menu } from '@lucide/svelte';
	import { Button, Sheet } from '@sivir-ui/svelte';
	import '../app.css';
	import AuthModeWarning from '$lib/components/AuthModeWarning.svelte';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	let drawerOpen = $state(false);
	let searchOpen = $state(false);
</script>

<AuthModeWarning authEnabled={data.capabilities.auth_enabled} />

<a
	href="#main"
	class="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50
		focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-[var(--elevation-float)]"
>
	Skip to content
</a>

<div class="flex min-h-screen">
	<!--
	  A fixed rail, not a column in the page flow: the navigation and the
	  library list stay put while a document list or a conversation scrolls
	  past them.
	-->
	<aside
		class="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-border bg-muted/40
			lg:block"
	>
		<Sidebar
			libraries={data.libraries}
			capabilities={data.capabilities}
			onsearch={() => (searchOpen = true)}
		/>
	</aside>

	<!--
	  The same sidebar in a drawer below the breakpoint, rather than a
	  separate set of mobile navigation that could drift from this one.
	-->
	<Sheet.Root bind:open={drawerOpen}>
		<Sheet.Content side="left" class="w-72 p-0">
			<Sidebar
				libraries={data.libraries}
				capabilities={data.capabilities}
				bindShortcut={false}
				onsearch={() => {
					drawerOpen = false;
					searchOpen = true;
				}}
				onnavigate={() => (drawerOpen = false)}
			/>
		</Sheet.Content>
	</Sheet.Root>

	<div class="flex min-w-0 flex-1 flex-col">
		<div class="flex items-center gap-3 border-b border-border px-4 py-2 lg:hidden">
			<Button variant="ghost" size="icon" onclick={() => (drawerOpen = true)}>
				<Menu size={16} aria-hidden="true" />
				<span class="sr-only">Open navigation</span>
			</Button>
			<span class="text-sm font-semibold tracking-[-0.02em]">Primer</span>
		</div>

		<!--
		  A flex column, so a page that wants the full height can ask for it
		  with flex-1 instead of subtracting this frame's own padding from
		  100vh and going wrong whenever the padding changes.
		-->
		<main id="main" class="flex min-w-0 flex-1 flex-col px-6 py-8 lg:px-10">
			{@render children()}
		</main>
	</div>
</div>

<CommandPalette
	bind:open={searchOpen}
	libraries={data.libraries}
	capabilities={data.capabilities}
/>
