<script lang="ts">
	import { Menu, TriangleAlert } from '@lucide/svelte';
	import { Button, Sheet } from '@sivir-ui/svelte';
	import '../app.css';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	let drawerOpen = $state(false);
	let searchOpen = $state(false);
</script>

<a
	href="#main"
	class="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50
		focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-[var(--elevation-float)]"
>
	Skip to content
</a>

<!--
  Exactly the height of the window, and no taller. The page itself never
  scrolls; the content region does. Anything that added height out here - a
  banner across the top, say - gave every screen a scrollbar whether or not
  it had anything to scroll.
-->
<div class="flex h-screen overflow-hidden">
	<!--
	  A rail, not a column in the page flow: the navigation and the library
	  list stay put while a document list or a conversation scrolls past them.
	-->
	<aside
		class="hidden h-full w-60 shrink-0 border-r border-border bg-muted/40 lg:block"
	>
		<Sidebar
			libraries={data.libraries}
			capabilities={data.capabilities}
			principal={data.principal}
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
				principal={data.principal}
				bindShortcut={false}
				onsearch={() => {
					drawerOpen = false;
					searchOpen = true;
				}}
				onnavigate={() => (drawerOpen = false)}
			/>
		</Sheet.Content>
	</Sheet.Root>

	<div class="flex min-w-0 flex-1 flex-col overflow-hidden">
		<div class="flex items-center gap-3 border-b border-border px-4 py-2 lg:hidden">
			<Button variant="ghost" size="icon" onclick={() => (drawerOpen = true)}>
				<Menu size={16} aria-hidden="true" />
				<span class="sr-only">Open navigation</span>
			</Button>
			<span class="text-sm font-semibold tracking-[-0.02em]">Primer</span>
			{#if !data.capabilities.auth_enabled}
				<!--
				  Beside the wordmark rather than behind the drawer it opens: the
				  full warning lives in the sidebar, but on a narrow screen that
				  is a tap away, which is the one state this warning must not be
				  in. This marker is the part that has to be seen without
				  tapping anything; opening the drawer is only how to read the
				  rest of it. Inline in the existing bar, not a row of its own,
				  so it costs no height - the page still fits the window with
				  nothing to scroll.
				-->
				<button
					type="button"
					onclick={() => (drawerOpen = true)}
					title="No authentication: everyone who can reach this page shares one account."
					class="ml-auto flex shrink-0 items-center gap-1 rounded-md border border-warning/40
						bg-warning/10 px-2 py-1 text-[11px] font-medium text-warning
						focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
				>
					<TriangleAlert size={12} aria-hidden="true" />
					No auth
				</button>
			{/if}
		</div>

		<!--
		  A flex column, so a page that wants the full height can ask for it
		  with flex-1 instead of subtracting this frame's own padding from
		  100vh and going wrong whenever the padding changes.
		-->
		<!--
		  Ordinary block flow, and the only thing in the frame that scrolls.
		  Not a flex column: most pages are a document that should simply run
		  on and scroll, and making every one of them a flex item means each
		  has to think about shrinking. A page that wants the full height
		  instead asks with `h-full`, which works because this has one.
		-->
		<main
			id="main"
			class="min-h-0 min-w-0 flex-1 overflow-y-auto px-6 py-8 lg:px-10"
		>
			{@render children()}
		</main>
	</div>
</div>

<CommandPalette
	bind:open={searchOpen}
	libraries={data.libraries}
	capabilities={data.capabilities}
/>
