<script lang="ts">
	import { Library, Link2Off, MessageSquare, Trash2, TriangleAlert } from '@lucide/svelte';
	import { Button } from '@sivir-ui/svelte';
	import type { ConversationSummary, LibrarySummary } from '$lib/api/types';
	import { exactly, timeAgo } from '$lib/when';

	interface Props {
		conversations: ConversationSummary[];
		/** To name the library each was asked of, and to notice a missing one. */
		libraries: LibrarySummary[];
		/** The conversation on screen, so the list can say which one it is. */
		openId?: string | null;
		/** One being deleted, so it stops accepting clicks while it goes. */
		busyId?: string | null;
		ondelete?: (conversation: ConversationSummary) => void;
		/** Called after opening one, so a drawer can close itself. */
		onopen?: () => void;
	}

	let { conversations, libraries, openId = null, busyId = null, ondelete, onopen }: Props = $props();

	/**
	 * What a conversation was asked of.
	 *
	 * Three states, not two. A conversation with no library was answered by
	 * the model alone and always will be; one whose library has since been
	 * deleted was grounded in documents that are gone, which is why its old
	 * answers cite things this deployment can no longer show. Collapsing
	 * those into "no library" would make a broken thread look like a
	 * deliberate one.
	 */
	function grounding(conversation: ConversationSummary) {
		if (conversation.library_id === null) {
			return { label: 'No library', icon: Link2Off, tone: 'text-muted-foreground' };
		}
		const library = libraries.find((candidate) => candidate.id === conversation.library_id);
		if (library) return { label: library.name, icon: Library, tone: 'text-muted-foreground' };
		return { label: 'Library deleted', icon: TriangleAlert, tone: 'text-error' };
	}
</script>

<div class="flex h-full min-h-0 flex-col gap-2">
	<h2 class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
		History
	</h2>

	{#if conversations.length === 0}
		<!--
		  Said rather than left blank. An empty column reads as something that
		  failed to load, and the first thing a new user sees here is nothing.
		-->
		<p class="px-1 text-xs text-muted-foreground">
			Conversations you have had appear here, newest first.
		</p>
	{/if}

	<ul class="min-h-0 flex-1 space-y-1 overflow-y-auto">
		{#each conversations as conversation (conversation.id)}
			{@const asked = grounding(conversation)}
			{@const open = conversation.id === openId}
			{@const going = conversation.id === busyId}
			<li class="group relative {going ? 'pointer-events-none opacity-50' : ''}">
				<!--
				  A link, not a button: a conversation has a URL, and the
				  ordinary things one does with one - a new tab, a bookmark, the
				  back button - should work.
				-->
				<a
					href="/chat?conversation={conversation.id}"
					onclick={onopen}
					aria-current={open ? 'page' : undefined}
					class="block rounded-md px-2.5 py-2 pr-9 transition-colors
						focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]
						{open ? 'bg-card shadow-[var(--elevation-1)]' : 'hover:bg-field-hover'}"
				>
					<span class="flex items-start gap-2">
						<MessageSquare
							size={14}
							aria-hidden="true"
							class="mt-0.5 shrink-0 text-muted-foreground"
						/>
						<span class="min-w-0 flex-1">
							<span class="line-clamp-2 text-sm leading-snug">{conversation.title}</span>
							<span class="mt-1 flex items-center gap-1.5 text-[11px] {asked.tone}">
								<asked.icon size={11} aria-hidden="true" class="shrink-0" />
								<span class="truncate">{asked.label}</span>
								<span aria-hidden="true">·</span>
								<time datetime={conversation.updated_at} title={exactly(conversation.updated_at)}>
									{timeAgo(conversation.updated_at)}
								</time>
							</span>
						</span>
					</span>
				</a>

				<!--
				  Kept out of the link, because a delete control inside a link
				  is a click that does one of two very different things
				  depending on a pixel. Visible on hover and on focus, so it is
				  reachable by keyboard rather than only by pointer.
				-->
				<Button
					variant="ghost"
					size="icon"
					class="absolute right-1 top-1.5 opacity-0 transition-opacity
						group-hover:opacity-100 focus-visible:opacity-100"
					onclick={() => ondelete?.(conversation)}
				>
					<Trash2 size={14} aria-hidden="true" />
					<span class="sr-only">Delete “{conversation.title}”</span>
				</Button>
			</li>
		{/each}
	</ul>
</div>
