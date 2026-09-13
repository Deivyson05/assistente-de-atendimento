'use client';
import { sendMessage } from "@/api";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { getLS, setLS } from "@/lib/utils";

import { PaperPlaneIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

type Mensagem = {
    dono: "user" | "assistant" | "erro";
    message: string;
    time: string;
};

const horaAtual = () =>
    new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export function ChatCard() {
    const [message, setMessage] = useState("");
    const [conversa, setConversa] = useState<Mensagem[]>([]);
    const [carregando, setCarregando] = useState(false);
    const fimDaLista = useRef<HTMLDivElement>(null);

    // localStorage só existe no navegador: ler dentro do useEffect evita o erro
    // durante o pre-render do Next.js
    useEffect(() => {
        const salva = getLS("conversa");
        if (Array.isArray(salva)) setConversa(salva);
    }, []);

    useEffect(() => {
        if (conversa.length > 0) setLS("conversa", conversa);
        fimDaLista.current?.scrollIntoView({ behavior: "smooth" });
    }, [conversa]);

    const obterSessionId = () => {
        let sessionId = getLS("sessionId");
        if (!sessionId) {
            sessionId = Math.random().toString(36).substring(2);
            setLS("sessionId", sessionId);
        }
        return sessionId;
    };

    const handleSendMessage = async () => {
        const texto = message.trim();
        if (!texto || carregando) return;

        // a mensagem do usuário aparece na hora, sem esperar a resposta
        setConversa((atual) => [
            ...atual,
            { dono: "user", message: texto, time: horaAtual() },
        ]);
        setMessage("");
        setCarregando(true);

        try {
            const response = await sendMessage(texto, obterSessionId());
            setConversa((atual) => [
                ...atual,
                {
                    dono: "assistant",
                    message: response.data.message,
                    time: horaAtual(),
                },
            ]);
        } catch (error) {
            console.error("Erro ao enviar mensagem:", error);
            setConversa((atual) => [
                ...atual,
                {
                    dono: "erro",
                    message:
                        "Não consegui falar com o servidor. Verifique sua conexão e tente de novo.",
                    time: horaAtual(),
                },
            ]);
        } finally {
            setCarregando(false);
        }
    };

    const estiloBolha = (dono: Mensagem["dono"]) => {
        if (dono === "user") return "bg-blue-500 text-white";
        if (dono === "erro") return "bg-red-100 text-red-700 border border-red-300";
        return "bg-gray-300 text-gray-800";
    };

    return (
        <Dialog>
            <DialogTrigger className="fixed bottom-4 right-4 bg-primary text-white rounded-full p-4 shadow-lg hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 cursor-pointer">
                Assistente Virtual
            </DialogTrigger>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Assistente</DialogTitle>
                    <DialogDescription>
                        Tirar dúvidas ou agendar consultas
                    </DialogDescription>
                </DialogHeader>
                <div className="flex flex-col space-y-2 overflow-y-auto max-h-96 mb-4">
                    {conversa.length === 0 && !carregando && (
                        <p className="text-sm text-gray-500 py-4 text-center">
                            Pergunte sobre serviços, horários ou convênios — ou peça
                            para marcar uma consulta.
                        </p>
                    )}

                    {conversa.map((item, index) => (
                        <div
                            key={index}
                            className={`flex flex-col ${item.dono === "user" ? "items-end" : "items-start"}`}
                        >
                            <span className="text-xs text-gray-500">{item.time}</span>
                            <div
                                className={`${estiloBolha(item.dono)} rounded-lg p-3 max-w-xs whitespace-pre-wrap break-words`}
                            >
                                {item.message}
                            </div>
                        </div>
                    ))}

                    {carregando && (
                        <div className="flex flex-col items-start">
                            <div className="bg-gray-300 text-gray-800 rounded-lg p-3">
                                <span className="inline-flex gap-1">
                                    <span className="animate-bounce">.</span>
                                    <span className="animate-bounce [animation-delay:150ms]">.</span>
                                    <span className="animate-bounce [animation-delay:300ms]">.</span>
                                </span>
                            </div>
                        </div>
                    )}

                    <div ref={fimDaLista} />
                </div>
                <div className="flex items-center justify-between rounded-xl overflow-hidden border border-gray-300">
                    <input
                        type="text"
                        placeholder={carregando ? "Aguardando resposta..." : "Mensagem..."}
                        className="flex-1 p-2 outline-none disabled:bg-gray-50"
                        value={message}
                        disabled={carregando}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") handleSendMessage();
                        }}
                    />
                    <button
                        type="submit"
                        className="bg-primary p-2 text-white cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={carregando || !message.trim()}
                        onClick={handleSendMessage}
                    >
                        <PaperPlaneIcon size={24} />
                    </button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
