import axios from "axios";

const backendUrl = process.env.REACT_APP_BACKEND_URL;
if (!backendUrl) throw new Error("REACT_APP_BACKEND_URL is required");

export const api = axios.create({ baseURL: `${backendUrl}/api`, timeout: 15000 });

export const messageFromError = (error: any) => error?.response?.data?.detail || error?.message || "Something went wrong";