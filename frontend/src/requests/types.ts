import type * as ImagePicker from "expo-image-picker";

export type PhotoAsset = ImagePicker.ImagePickerAsset;
export type Quote = {
  quote_id: string;
  specialist_id: string;
  specialist_name: string;
  price: number;
  currency: string;
  description: string;
  estimated_time: string;
  status: "pending" | "accepted" | "rejected";
  conversation_id?: string;
};
export type RequestItem = {
  request_id: string;
  title: string;
  description: string;
  category: string;
  photos: string[];
  city: string;
  status: string;
  created_at: string;
  distance_km?: number;
  quotes?: Quote[];
  quotes_count?: number;
  my_quote?: { quote_id: string; price: number; status: string } | null;
};
export type Zone = { province: { code: string; name: string } | null; lat: number | null; lng: number | null };
