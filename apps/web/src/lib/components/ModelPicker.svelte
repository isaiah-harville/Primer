<script lang="ts">
	import { Cpu, TriangleAlert } from '@lucide/svelte';
	import { DropdownMenu } from '@sivir-ui/svelte';
	import type { ChatModel } from '$lib/api/types';
	import { qualify } from '$lib/models';

	interface Props {
		models: ChatModel[];
		/**
		 * The chosen model, as "<provider id>:<model id>".
		 *
		 * Qualified because model names are not unique across providers - two
		 * endpoints serving `llama3.1:8b` is ordinary - so the name alone
		 * cannot say which endpoint a question should go to.
		 */
		value?: string;
		/**
		 * Why there is no model, when there is none. Null when all is well.
		 *
		 * Carried as a sentence rather than a flag because the causes need
		 * different fixes: an inference endpoint that is down, one that is up
		 * with nothing loaded, and a Chat service that cannot be reached at
		 * all are three different jobs for whoever runs this.
		 */
		problem?: string | null;
	}

	let { models, value = $bindable(''), problem = null }: Props = $props();

	let chosen = $derived(models.find((model) => qualify(model) === value));
	let fallback = $derived(models.find((model) => model.default) ?? models[0]);
	let shown = $derived(chosen ?? fallback);

	//: Whether there is anything to pick between. Most deployments serve one
	//: model, and a menu with a single entry is a control that does nothing.
	let choosable = $derived(models.length > 1);

	//: Grouped so a reader can see where each model runs. With one provider
	//: the heading would be noise, so it is only drawn when there are two.
	let byProvider = $derived.by(() => {
		const groups = new Map<string, ChatModel[]>();
		for (const model of models) {
			const name = model.provider_name ?? 'This deployment';
			groups.set(name, [...(groups.get(name) ?? []), model]);
		}
		return [...groups];
	});
</script>

<!--
  Always says which model is answering, even when there is no choice to make.

  It used to hide itself entirely whenever a deployment served one model,
  which is the common case - so the usual experience was a chat window that
  never named the thing writing the answers. Which model wrote an answer is a
  fact about the answer, not a preference, and it belongs on screen whether
  or not it can be changed.
-->
{#if shown === undefined}
	<!--
	  No model, and the reason. Not a picker in an error colour: there is
	  nothing to pick, and a control implies otherwise. This used to show the
	  configured default name, which meant an endpoint that was down looked
	  exactly like one that was up.
	-->
	<span
		class="flex items-center gap-2 px-1 py-1.5 text-sm text-error"
		title={problem ?? 'No model is available.'}
	>
		<TriangleAlert size={14} aria-hidden="true" />
		<span class="max-w-[22rem] truncate">No model available</span>
	</span>
{:else if choosable}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger variant="ghost" size="sm" class="text-muted-foreground">
			<Cpu size={14} aria-hidden="true" />
			<span
				class="max-w-[16rem] truncate font-mono text-xs"
				title="{shown.id}{shown.provider_name ? ` on ${shown.provider_name}` : ''}"
			>
				{shown.id}
			</span>
		</DropdownMenu.Trigger>
		<DropdownMenu.Content>
			<DropdownMenu.RadioGroup
				value={value || qualify(shown)}
				onValueChange={(next) => (value = next)}
			>
				{#each byProvider as [provider, offered], index (provider)}
					{#if byProvider.length > 1}
						<!--
						  Which machine each model runs on is the thing being
						  chosen between as much as the model is: the local one
						  is free and private, the hosted one is neither.
						-->
						<p
							class="px-2.5 pb-1 font-mono text-[10px] uppercase tracking-[0.09em]
								text-muted-foreground {index > 0 ? 'pt-2' : 'pt-1'}"
						>
							{provider}
						</p>
					{/if}
					{#each offered as model (qualify(model))}
						<DropdownMenu.RadioItem value={qualify(model)}>
							<span class="flex w-full items-center justify-between gap-4">
								<span class="truncate">{model.id}</span>
								{#if model.default}
									<span class="text-xs text-muted-foreground">Default</span>
								{/if}
							</span>
						</DropdownMenu.RadioItem>
					{/each}
				{/each}
			</DropdownMenu.RadioGroup>
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{:else}
	<!--
	  One model: plain text rather than a dead menu, so nothing invites a
	  click that leads nowhere.
	-->
	<span
		class="flex items-center gap-2 px-1 py-1.5 text-sm text-muted-foreground"
		title="Answered by {shown.id}{shown.provider_name
			? ` on ${shown.provider_name}`
			: ''}. This deployment serves one model."
	>
		<Cpu size={14} aria-hidden="true" />
		<span class="max-w-[16rem] truncate font-mono text-xs">{shown.id}</span>
	</span>
{/if}
