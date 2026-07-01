export interface Doctor {
    id: string;
    name: string;
    specialization: string;
    qualifications: string;  // e.g. "MBBS / MD / RMP"
    timings: string;         // e.g. "Mon–Sun  02:00 PM – 12:00 AM"
    available: boolean;
    status?: string;         // available | busy | offline | on_leave
    fee: string;             // e.g. "Rs. 1,500"
    department?: string;
    onLeave?: boolean;
}
