import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import Purchases, { LOG_LEVEL } from "react-native-purchases";
import type { CustomerInfo, PurchasesPackage } from "react-native-purchases";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

const REVENUECAT_TEST_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_TEST_API_KEY;
const REVENUECAT_IOS_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY;
const REVENUECAT_ANDROID_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY;

export const REVENUECAT_ENTITLEMENT_IDENTIFIER = "pro";
export const rcEnabled = Platform.OS !== "web" || __DEV__;
export const rcSimulated = Platform.OS === "web" || __DEV__;

function getRevenueCatApiKey() {
  if (!REVENUECAT_TEST_API_KEY || !REVENUECAT_IOS_API_KEY || !REVENUECAT_ANDROID_API_KEY) {
    throw new Error("RevenueCat public API keys not found");
  }
  if (Platform.OS === "web" || __DEV__) return REVENUECAT_TEST_API_KEY;
  if (Platform.OS === "ios") return REVENUECAT_IOS_API_KEY;
  if (Platform.OS === "android") return REVENUECAT_ANDROID_API_KEY;
  return REVENUECAT_TEST_API_KEY;
}

export function initializeRevenueCat() {
  if (!rcEnabled) return;
  Purchases.setLogLevel(__DEV__ ? LOG_LEVEL.DEBUG : LOG_LEVEL.WARN);
  Purchases.configure({ apiKey: getRevenueCatApiKey() });
}

function useSubscriptionContext(userId: string | null) {
  const queryClient = useQueryClient();
  const rcIdentityRef = useRef<string | null>(null);
  const [identityError, setIdentityError] = useState<string | null>(null);

  useEffect(() => {
    if (!rcEnabled) return;
    (async () => {
      try {
        if (userId && rcIdentityRef.current !== userId) {
          const { customerInfo } = await Purchases.logIn(userId);
          rcIdentityRef.current = userId;
          setIdentityError(null);
          queryClient.setQueryData(["revenuecat", "customer-info"], customerInfo);
        } else if (!userId && rcIdentityRef.current) {
          await Purchases.logOut();
          rcIdentityRef.current = null;
        }
      } catch (e) {
        setIdentityError(String(e));
      }
    })();
  }, [userId, queryClient]);

  const customerInfoQuery = useQuery({
    queryKey: ["revenuecat", "customer-info"],
    queryFn: () => Purchases.getCustomerInfo(),
    enabled: rcEnabled && !!userId,
    staleTime: 60 * 1000,
  });

  const offeringsQuery = useQuery({
    queryKey: ["revenuecat", "offerings"],
    queryFn: () => Purchases.getOfferings(),
    enabled: rcEnabled && !!userId,
    staleTime: 300 * 1000,
  });

  useEffect(() => {
    if (!rcEnabled) return;
    const listener = (info: CustomerInfo) => queryClient.setQueryData(["revenuecat", "customer-info"], info);
    Purchases.addCustomerInfoUpdateListener(listener);
    return () => {
      Purchases.removeCustomerInfoUpdateListener(listener);
    };
  }, [queryClient]);

  const purchaseMutation = useMutation({
    mutationFn: async (pkg: PurchasesPackage) => {
      const id = (await Purchases.getCustomerInfo()).originalAppUserId;
      if (id.startsWith("$RCAnonymousID:")) throw new Error("identity_not_ready");
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      return customerInfo;
    },
  });

  const restoreMutation = useMutation({ mutationFn: () => Purchases.restorePurchases() });

  const entitlement = customerInfoQuery.data?.entitlements.active?.[REVENUECAT_ENTITLEMENT_IDENTIFIER];
  const originalAppUserId = customerInfoQuery.data?.originalAppUserId;
  const identityReady = !!originalAppUserId && !originalAppUserId.startsWith("$RCAnonymousID:");

  return {
    customerInfo: customerInfoQuery.data,
    offerings: offeringsQuery.data,
    offeringsError: offeringsQuery.error,
    entitlement,
    isSubscribed: entitlement !== undefined,
    identityReady,
    identityError,
    isLoading: customerInfoQuery.isLoading || offeringsQuery.isLoading,
    purchase: purchaseMutation.mutateAsync,
    restore: restoreMutation.mutateAsync,
    isPurchasing: purchaseMutation.isPending,
    isRestoring: restoreMutation.isPending,
  };
}

type Value = ReturnType<typeof useSubscriptionContext>;
const Context = createContext<Value | null>(null);

export function SubscriptionProvider({ userId, children }: { userId: string | null; children: React.ReactNode }) {
  const value = useSubscriptionContext(userId);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSubscription() {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useSubscription must be used within a SubscriptionProvider");
  return ctx;
}
