import { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { useToast } from "../../ui/Toast";

/**
 * Run a hold action (Pause, Stop, Resume, Block, Unblock, Start worker).
 * `act(name, call, sentence)` calls `call(client)`, says `sentence(result)`
 * in the toast and runs `onChanged`; a refusal is `notice` (the API's
 * sentence) where the action was. `pending` names the action in flight.
 * `client` and `show` are for an action behind a dialog, which shows its own
 * refusal.
 */
export function useHoldAction({ onChanged } = {}) {
  const client = useApiClient();
  const { show } = useToast();
  const [pending, setPending] = useState(null);
  const [notice, setNotice] = useState(null);

  async function act(name, call, sentence) {
    setPending(name);
    setNotice(null);
    try {
      const result = await call(client);
      show(sentence(result));
      onChanged?.();
      return result;
    } catch (error) {
      setNotice(errorSentence(error));
      return null;
    } finally {
      setPending(null);
    }
  }

  return { pending, busy: pending !== null, notice, setNotice, act, client, show };
}
