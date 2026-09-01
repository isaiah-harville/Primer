<script lang="ts">
	import { page } from '$app/state';
	import { Library, MessageSquare, Search } from '@lucide/svelte';
	import { Shortcut } from '@sivir-ui/svelte';
	import type { DeploymentCapabilities, LibrarySummary } from '$lib/api/types';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';

	interface Props {
		libraries: LibrarySummary[];
		capabilities: DeploymentCapabilities;
		onsearch?: () => void;
		/** Called after any navigation, so the mobile drawer can close itself. */
		onnavigate?: () => void;
		/**
		 * Whether this copy registers the search key. Shortcut binds a window
		 * handler and clicks the control it sits in, so exactly one copy may
		 * carry it; the drawer's copy passes false and the always-mounted rail
		 * keeps it, which is what makes the key work at every width.
		 */
		bindShortcut?: boolean;
	}

	let {
		libraries,
		capabilities,
		onsearch,
		onnavigate,
		bindShortcut = true
	}: Props = $props();

	let sections = $derived(
		[
			{ href: '/libraries', label: 'Libraries', icon: Library, show: true },
			{ href: '/chat', label: 'Chat', icon: MessageSquare, show: capabilities.chat_available }
		].filter((section) => section.show)
	);

	// Prefix rather than equality, so a document list keeps Libraries lit.
	function inSection(href: string): boolean {
		return page.url.pathname === href || page.url.pathname.startsWith(`${href}/`);
	}
</script>

<div class="flex h-full min-h-0 flex-col gap-5 px-3 py-4">
	<a
		href="/libraries"
		onclick={onnavigate}
		class="px-2 text-[15px] font-semibold tracking-[-0.02em] focus-visible:outline-none
			focus-visible:shadow-[var(--focus-ring)]"
	>
		Primer
	</a>

	<!--
	  Shaped like the field it opens rather than like a button, and it prints
	  the key that opens it. A palette nobody knows the shortcut for is a
	  palette nobody uses, and the shortcut is the reason it is worth having.
	-->
	<button
		type="button"
		onclick={onsearch}
		class="flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5
			text-left text-sm text-muted-foreground transition-colors hover:bg-field-hover
			focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
	>
		<Search size={14} aria-hidden="true" />
		<span class="flex-1">Search</span>
		{#if bindShortcut}
			<Shortcut shortcut="cmd+k" class="pointer-events-none" />
		{/if}
	</button>

	<nav aria-label="Main" class="flex flex-col gap-0.5">
		{#each sections as section (section.href)}
			<a
				href={section.href}
				onclick={onnavigate}
				aria-current={inSection(section.href) ? 'page' : undefined}
				class="flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors
					focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]
					{inSection(section.href)
					? 'bg-secondary font-medium text-foreground'
					: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
			>
				<section.icon size={15} aria-hidden="true" />
				{section.label}
			</a>
		{/each}
	</nav>

	<!--
	  The libraries themselves, listed on every screen. Which library you are
	  in is the context for everything else here, so switching should not mean
	  navigating back to a list first.
	-->
	{#if libraries.length > 0}
		<div class="flex min-h-0 flex-1 flex-col">
			<h2
				class="px-2.5 pb-1 font-mono text-[10px] uppercase tracking-[0.09em]
					text-muted-foreground"
			>
				Libraries
			</h2>
			<ul class="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
				{#each libraries as library (library.id)}
					{@const active = page.url.pathname === `/libraries/${library.id}`}
					<li>
						<a
							href="/libraries/{library.id}"
							onclick={onnavigate}
							aria-current={active ? 'page' : undefined}
							class="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm
								transition-colors focus-visible:outline-none
								focus-visible:shadow-[var(--focus-ring)]
								{active
								? 'bg-secondary font-medium text-foreground'
								: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
						>
							<span class="min-w-0 flex-1 truncate" title={library.name}>
								{library.name}
							</span>
							<span class="font-mono text-[11px] tabular-nums text-muted-foreground">
								{library.document_count}
							</span>
						</a>
					</li>
				{/each}
			</ul>
		</div>
	{:else}
		<div class="flex-1"></div>
	{/if}

	<div class="flex items-center justify-between border-t border-border px-1 pt-3">
		<span class="px-1.5 font-mono text-[10px] uppercase tracking-[0.09em] text-muted-foreground">
			{capabilities.auth_enabled ? 'Signed in' : 'No auth'}
		</span>
		<ThemeToggle />
	</div>
</div>
