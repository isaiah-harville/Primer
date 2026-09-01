<script lang="ts">
	import {
		Alert,
		Button,
		Conversation,
		Markdown,
		Message,
		PromptComposer
	} from '@sivir-ui/svelte';
	import CitationPanel from '$lib/components/CitationPanel.svelte';
	import LibraryLink from '$lib/components/LibraryLink.svelte';
	import ResponseActions from '$lib/components/ResponseActions.svelte';
	import { emptyStream, parseEvents, reduce, type StreamState } from '$lib/api/sse';
	import type { MessageSummary } from '$lib/api/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Empty means no library, which is a usable state rather than a missing
	// one: the model answers on its own. Nothing is chosen by default,
	// because silently attaching the first library would make an answer look
	// grounded in something the user never picked.
	let libraryId = $state('');
	let question = $state('');
	let turns = $state<{ question: string; stream: StreamState }[]>([]);
	let streaming = $state(false);
	let sourcesOpen = $state(false);
	let sourcesFor = $state<StreamState | null>(null);

	async function ask() {
		const asked = question.trim();
		if (!asked || streaming) return;

		question = '';
		streaming = true;
		const turn = { question: asked, stream: emptyStream() };
		turns = [...turns, turn];

		try {
			const response = await fetch('/chat/ask', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				// Omitted rather than sent empty when nothing is linked: the
				// absence of a library is what asks for an uncited answer.
				body: JSON.stringify(
					libraryId ? { library_id: libraryId, message: asked } : { message: asked }
				)
			});
			if (!response.body) throw new Error('The server sent no response body.');

			for await (const event of parseEvents(response.body)) {
				// Reassigning the array is what makes Svelte see the change;
				// the state object itself is replaced by the reducer.
				turn.stream = reduce(turn.stream, event);
				turns = [...turns];
			}
		} catch {
			turn.stream = {
				...turn.stream,
				error: { code: 'connection_lost', detail: 'The connection closed before the answer finished.' },
				done: true
			};
			turns = [...turns];
		} finally {
			streaming = false;
		}
	}

	function completed(stream: StreamState): MessageSummary | null {
		if (stream.message) return stream.message;
		// A failed stream still has an answer worth copying: the text it
		// managed to write before it stopped.
		if (!stream.error || !stream.messageId) return null;
		return {
			id: stream.messageId,
			conversation_id: stream.conversationId ?? '',
			role: 'assistant',
			state: 'failed',
			content: stream.text,
			citations: stream.citations,
			error_code: stream.error.code,
			created_at: new Date().toISOString()
		};
	}
</script>

<h1 class="text-xl font-semibold tracking-[-0.02em]">Chat</h1>

<!--
  Constrained here rather than in the frame. Answers are prose, and prose set
  the full width of a desktop window is unreadable - but the frame around it
  holds tables that need every pixel.
-->
<div class="mx-auto mt-6 flex min-h-0 w-full max-w-3xl flex-1 flex-col">
	<Conversation.Root class="flex-1">
		<Conversation.Content>
			{#if turns.length === 0}
				<Conversation.Empty>
					{#if libraryId}
						Ask a question about this library. Every answer cites the passages it used.
					{:else}
						Ask anything. Link a library below to have answers drawn from your own
						documents and cited.
					{/if}
				</Conversation.Empty>
			{/if}

			{#each turns as turn, index (index)}
				<Message.Root from="user">
					<Message.Content>{turn.question}</Message.Content>
				</Message.Root>

				<Message.Root from="assistant" status={turn.stream.done ? 'idle' : 'streaming'}>
					<Message.Content>
						<!--
						  Rendered as Markdown, since models write it. The text
						  is the model's, so it is rendered rather than
						  interpreted: nothing here acts on it.
						-->
						<Markdown content={turn.stream.text} />
					</Message.Content>

					{#if turn.stream.error}
						<Alert.Root variant="error" class="mt-2">
							<Alert.Description>
								{turn.stream.error.detail ?? 'The answer stopped before it finished.'}
							</Alert.Description>
						</Alert.Root>
					{/if}

					{#if turn.stream.done}
						{@const message = completed(turn.stream)}
						{#if message}
							<Message.Actions>
								<ResponseActions
									{message}
									onshowsources={() => {
										sourcesFor = turn.stream;
										sourcesOpen = true;
									}}
								/>
							</Message.Actions>
						{/if}
					{/if}
				</Message.Root>
			{/each}
		</Conversation.Content>
		<Conversation.ScrollButton />
	</Conversation.Root>

	<PromptComposer.Root
		bind:value={question}
		status={streaming ? 'submitting' : 'idle'}
		onSubmit={ask}
		class="mt-4"
	>
		<PromptComposer.Input
			placeholder={libraryId ? 'Ask about this library…' : 'Ask anything…'}
			aria-label="Your question"
		/>
		<PromptComposer.Toolbar>
			<PromptComposer.Actions>
				<PromptComposer.Submit />
			</PromptComposer.Actions>
		</PromptComposer.Toolbar>
	</PromptComposer.Root>

	<!--
	  Below the composer, because whether this question is answered from your
	  documents belongs with asking it rather than with the page around it.
	-->
	<div class="mt-2 flex items-center justify-between gap-3">
		<LibraryLink libraries={data.libraries} bind:value={libraryId} />

		{#if !libraryId}
			<p class="text-xs text-muted-foreground">Answers will not be cited.</p>
		{/if}
	</div>
</div>

{#if sourcesFor}
	<CitationPanel citations={sourcesFor.citations} bind:open={sourcesOpen} />
{/if}
