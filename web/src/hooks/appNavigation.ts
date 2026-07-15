"use client";

import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { useCallback } from "react";

interface UseAppRouterProps {
  chatSessionId?: string;
  agentId?: number;
  projectId?: number;
}

export function useAppRouter() {
  const router = useRouter();
  return useCallback(
    ({ chatSessionId, agentId, projectId }: UseAppRouterProps = {}) => {
      const finalParams = [];

      if (chatSessionId)
        finalParams.push(`${SEARCH_PARAM_NAMES.CHAT_ID}=${chatSessionId}`);
      else if (agentId !== undefined && agentId !== null)
        finalParams.push(`${SEARCH_PARAM_NAMES.PERSONA_ID}=${agentId}`);
      else if (projectId !== undefined && projectId !== null)
        finalParams.push(`${SEARCH_PARAM_NAMES.PROJECT_ID}=${projectId}`);

      const finalString = finalParams.join("&");
      const finalUrl = `/app${finalString ? "?" + finalString : ""}`;

      router.push(finalUrl as Route);
    },
    [router]
  );
}

export function useAppParams() {
  const searchParams = useSearchParams();
  return useCallback((name: string) => searchParams.get(name), [searchParams]);
}
