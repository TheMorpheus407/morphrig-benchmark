#include "MorphRigData.h"
#include "MorphRig.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	TUniquePtr<FMorphRigData> GData;

	TSharedPtr<FJsonObject> LoadJson(const FString& File, FString& OutError)
	{
		FString Text;
		const FString Path = FMorphRigData::DataDir() / File;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			OutError += FString::Printf(TEXT("cannot read %s; "), *Path);
			return nullptr;
		}
		TSharedPtr<FJsonObject> Obj;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
		{
			OutError += FString::Printf(TEXT("cannot parse %s; "), *Path);
			return nullptr;
		}
		return Obj;
	}

	FVector ReadVec(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (O.IsValid() && O->TryGetArrayField(Field, A) && A->Num() >= 3)
		{
			return FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber());
		}
		return FVector::ZeroVector;
	}

	double Num(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, double Default = 0.0)
	{
		double V = Default;
		if (O.IsValid())
		{
			O->TryGetNumberField(Field, V);
		}
		return V;
	}

	FString Str(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		FString V;
		if (O.IsValid())
		{
			O->TryGetStringField(Field, V);
		}
		return V;
	}

	void ReadWeights(const TSharedPtr<FJsonObject>& O, TMap<FName, float>& Out)
	{
		if (!O.IsValid())
		{
			return;
		}
		for (const auto& KV : O->Values)
		{
			double V = 0.0;
			if (KV.Value.IsValid() && KV.Value->TryGetNumber(V))
			{
				Out.Add(FName(*KV.Key), (float)V);
			}
		}
	}
}

bool FMorphClip::HasEvent(FName InName) const
{
	for (const FMorphEvent& E : Events)
	{
		if (E.Name == InName)
		{
			return true;
		}
	}
	return false;
}

float FMorphClip::EventTime(FName InName, float Default) const
{
	for (const FMorphEvent& E : Events)
	{
		if (E.Name == InName)
		{
			return E.Time;
		}
	}
	return Default;
}

FString FMorphRigData::DataDir()
{
	return FPaths::ProjectContentDir() / TEXT("MorphRigData");
}

const FMorphRigData& FMorphRigData::Get()
{
	if (!GData.IsValid())
	{
		GData = MakeUnique<FMorphRigData>();
		GData->Load();
	}
	return *GData;
}

void FMorphRigData::Reload()
{
	GData.Reset();
	Get();
}

void FMorphRigData::Load()
{
	Error.Reset();
	// ------------------------------------------------------------------ manifest
	if (TSharedPtr<FJsonObject> M = LoadJson(TEXT("animation_manifest.json"), Error))
	{
		Fps = (float)Num(M, TEXT("fps"), 30.0);
		M->TryGetBoolField(TEXT("placeholder"), bPlaceholder);
		const TSharedPtr<FJsonObject>* Conv = nullptr;
		if (M->TryGetObjectField(TEXT("conventions"), Conv))
		{
			const TSharedPtr<FJsonObject>* Sp = nullptr;
			if ((*Conv)->TryGetObjectField(TEXT("nominal_speeds_cm_s"), Sp))
			{
				WalkSpeed = (float)Num(*Sp, TEXT("walk"), 150.0);
				RunSpeed = (float)Num(*Sp, TEXT("run"), 400.0);
				SprintSpeed = (float)Num(*Sp, TEXT("sprint"), 650.0);
			}
		}
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (M->TryGetArrayField(TEXT("clips"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				const TSharedPtr<FJsonObject> C = V->AsObject();
				if (!C.IsValid())
				{
					continue;
				}
				FMorphClip Clip;
				Clip.Id = FName(*Str(C, TEXT("id")));
				Clip.Form = Str(C, TEXT("form"));
				Clip.Layer = FName(*Str(C, TEXT("layer")));
				Clip.AssetPath = Str(C, TEXT("unreal_asset"));
				C->TryGetBoolField(TEXT("loop"), Clip.bLoop);
				C->TryGetBoolField(TEXT("is_pose"), Clip.bPose);
				Clip.bRootMotion = Str(C, TEXT("root_movement")) == TEXT("root_motion");
				Clip.FrameEnd = (int32)Num(C, TEXT("frame_end"));
				Clip.Duration = (float)Num(C, TEXT("duration"));
				Clip.NominalSpeed = (float)Num(C, TEXT("nominal_speed_cm_s"));
				Clip.TravelDirDeg = (float)Num(C, TEXT("travel_dir_deg"));
				Clip.Gait = FName(*Str(C, TEXT("gait")));
				Clip.TurnYawDeg = (float)Num(C, TEXT("turn_yaw_deg"));
				Clip.AimYawDeg = (float)Num(C, TEXT("aim_yaw_deg"));
				Clip.AimPitchDeg = (float)Num(C, TEXT("aim_pitch_deg"));
				Clip.HitFromDeg = (float)Num(C, TEXT("hit_from_deg"));
				// optional speed profile of start / stop / pivot clips: one value per frame along the facing at clip start.
				// Accepted: "speed_profile_cm_s": [...], "speed_profile": [...] (m/s as authored, or cm/s - detected by magnitude),
				// "speed_profile": {"cm_s": [...]} / {"m_s": [...]}.
				{
					const TArray<TSharedPtr<FJsonValue>>* SP = nullptr;
					bool bCm = false, bMetres = false;
					if (C->TryGetArrayField(TEXT("speed_profile_cm_s"), SP))
					{
						bCm = true;
					}
					else if (!C->TryGetArrayField(TEXT("speed_profile"), SP))
					{
						const TSharedPtr<FJsonObject>* SO = nullptr;
						if (C->TryGetObjectField(TEXT("speed_profile"), SO))
						{
							if ((*SO)->TryGetArrayField(TEXT("cm_s"), SP))
							{
								bCm = true;
							}
							else if ((*SO)->TryGetArrayField(TEXT("m_s"), SP))
							{
								bMetres = true;
							}
						}
					}
					if (SP)
					{
						float MaxAbs = 0.f;
						for (const TSharedPtr<FJsonValue>& ProfileValue : *SP)
						{
							Clip.SpeedProfile.Add((float)ProfileValue->AsNumber());
							MaxAbs = FMath::Max(MaxAbs, FMath::Abs(Clip.SpeedProfile.Last()));
						}
						if (bMetres || (!bCm && MaxAbs <= 30.f))
						{
							for (float& ProfileSpeed : Clip.SpeedProfile)
							{
								ProfileSpeed *= 100.f;
							}
						}
					}
					double Ph = 0.0;
					if (C->TryGetNumberField(TEXT("entry_phase"), Ph)) { Clip.EntryPhase = (float)Ph; }
					if (C->TryGetNumberField(TEXT("exit_phase"), Ph)) { Clip.ExitPhase = (float)Ph; }
				}
				if (!C->TryGetBoolField(TEXT("floor_contact"), Clip.bFloorContact))
				{
					// default when the manifest does not say: the clips whose hands / knees / body rest on the floor
					static const TCHAR* FloorPrefixes[] = { TEXT("knockdown_"), TEXT("getup_"), TEXT("prone_"), TEXT("sleep_"), TEXT("death_"), TEXT("dead_"),
						TEXT("respawn"), TEXT("land_heavy"), TEXT("cast_ground"), TEXT("deploy") };
					const FString IdStr = Clip.Id.ToString();
					for (const TCHAR* Prefix : FloorPrefixes)
					{
						Clip.bFloorContact |= IdStr.StartsWith(Prefix);
					}
				}
				const FString FinalPose = Str(C, TEXT("final_pose"));
				Clip.FinalPose = FinalPose.IsEmpty() ? NAME_None : FName(*FinalPose);
				const TSharedPtr<FJsonObject>* RM = nullptr;
				if (C->TryGetObjectField(TEXT("root_motion"), RM))
				{
					Clip.RootDisplacement = ReadVec(*RM, TEXT("displacement_cm"));
				}
				const TArray<TSharedPtr<FJsonValue>>* Ev = nullptr;
				if (C->TryGetArrayField(TEXT("events"), Ev))
				{
					for (const TSharedPtr<FJsonValue>& EV : *Ev)
					{
						const TSharedPtr<FJsonObject> E = EV->AsObject();
						FMorphEvent Event;
						Event.Name = FName(*Str(E, TEXT("name")));
						Event.Frame = (int32)Num(E, TEXT("frame"));
						Event.Time = (float)Num(E, TEXT("time"), Event.Frame / Fps);
						Event.Normalized = (float)Num(E, TEXT("normalized"), Clip.Duration > 0.f ? Event.Time / Clip.Duration : 0.f);
						Clip.Events.Add(Event);
					}
					Clip.Events.StableSort([](const FMorphEvent& A, const FMorphEvent& B) { return A.Time < B.Time; });
				}
				// prop tracks: [{prop, holder, start|frame_start, end|frame_end}] or [{prop, segments:[{holder,start,end}]}] (frames)
				const TArray<TSharedPtr<FJsonValue>>* PT = nullptr;
				if (C->TryGetArrayField(TEXT("prop_tracks"), PT))
				{
					auto ReadSeg = [&](const TSharedPtr<FJsonObject>& S, const FString& Prop)
					{
						if (!S.IsValid())
						{
							return;
						}
						FMorphPropSegment Seg;
						Seg.Prop = FName(*Prop);
						Seg.Holder = FName(*Str(S, TEXT("holder")));
						double A = 0.0, B = Clip.FrameEnd;
						if (!S->TryGetNumberField(TEXT("start"), A))
						{
							S->TryGetNumberField(TEXT("frame_start"), A);
						}
						if (!S->TryGetNumberField(TEXT("end"), B))
						{
							S->TryGetNumberField(TEXT("frame_end"), B);
						}
						Seg.Start = (float)A / Fps;
						Seg.End = (float)B / Fps;
						if (!Seg.Holder.IsNone() && !Seg.Prop.IsNone())
						{
							Clip.PropSegments.Add(Seg);
						}
					};
					for (const TSharedPtr<FJsonValue>& PV : *PT)
					{
						const TSharedPtr<FJsonObject> P = PV->AsObject();
						if (!P.IsValid())
						{
							continue;
						}
						const FString Prop = Str(P, TEXT("prop"));
						const TArray<TSharedPtr<FJsonValue>>* Segs = nullptr;
						if (P->TryGetArrayField(TEXT("segments"), Segs))
						{
							for (const TSharedPtr<FJsonValue>& SV : *Segs)
							{
								ReadSeg(SV->AsObject(), Prop);
							}
						}
						else
						{
							ReadSeg(P, Prop);
						}
					}
				}
				const TArray<FString> NoStrings;
				C->TryGetStringArrayField(TEXT("entry_states"), Clip.EntryStates);
				C->TryGetStringArrayField(TEXT("exit_states"), Clip.ExitStates);
				ClipIndex.Add(Clip.Id, Clips.Num());
				Clips.Add(MoveTemp(Clip));
			}
		}
	}
	// ------------------------------------------------------------------ skeleton
	if (TSharedPtr<FJsonObject> S = LoadJson(TEXT("skeleton_and_sockets.json"), Error))
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (S->TryGetArrayField(TEXT("bones"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				const TSharedPtr<FJsonObject> B = V->AsObject();
				FMorphBoneDef Def;
				Def.Name = FName(*Str(B, TEXT("name")));
				const FString Parent = Str(B, TEXT("parent"));
				Def.Parent = Parent.IsEmpty() ? NAME_None : FName(*Parent);
				Def.Role = Str(B, TEXT("role"));
				Def.LengthCm = (float)Num(B, TEXT("length_cm"));
				Def.RefPositionCS = ReadVec(B, TEXT("unreal_ref_position_cm"));
				if (Def.Role.Contains(TEXT("prop")))
				{
					PropBones.Add(Def.Name);
				}
				if (Def.Role.Contains(TEXT("secondary")))
				{
					SecondaryBones.Add(Def.Name);
				}
				Bones.Add(Def);
			}
		}
		const TSharedPtr<FJsonObject>* PB = nullptr;
		if (S->TryGetObjectField(TEXT("procedural_bones"), PB))
		{
			for (const auto& KV : (*PB)->Values)
			{
				const TSharedPtr<FJsonObject> R = KV.Value->AsObject();
				FMorphHelperRule Rule;
				Rule.Bone = FName(*KV.Key);
				Rule.Driver = FName(*Str(R, TEXT("driver")));
				const FString Kind = Str(R, TEXT("kind"));
				Rule.Kind = Kind == TEXT("untwist") ? FMorphHelperRule::Untwist : (Kind == TEXT("twist") ? FMorphHelperRule::Twist : FMorphHelperRule::Half);
				Rule.Amount = (float)Num(R, TEXT("amount"), 0.5);
				HelperRules.Add(Rule);
			}
		}
		if (S->TryGetArrayField(TEXT("sockets"), Arr))
		{
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				const TSharedPtr<FJsonObject> O = V->AsObject();
				FMorphSocketDef Def;
				Def.Name = FName(*Str(O, TEXT("name")));
				Def.Bone = FName(*Str(O, TEXT("bone")));
				Def.Position = ReadVec(O, TEXT("unreal_position_cm"));
				Def.Forward = ReadVec(O, TEXT("unreal_forward"));
				Def.Up = ReadVec(O, TEXT("unreal_up"));
				Sockets.Add(Def);
			}
		}
	}
	// ------------------------------------------------------------------ face
	if (TSharedPtr<FJsonObject> F = LoadJson(TEXT("face_controls.json"), Error))
	{
		TArray<FString> Names;
		if (F->TryGetStringArrayField(TEXT("morph_targets"), Names))
		{
			for (const FString& N : Names)
			{
				Morphs.Add(FName(*N));
			}
		}
		Names.Reset();
		if (F->TryGetStringArrayField(TEXT("controls"), Names))
		{
			for (const FString& N : Names)
			{
				Controls.Add(FName(*N));
			}
		}
		const TSharedPtr<FJsonObject>* BC = nullptr;
		if (F->TryGetObjectField(TEXT("bone_controls"), BC))
		{
			for (const auto& KV : (*BC)->Values)
			{
				TArray<FMorphBoneOffset>& List = BoneControls.Add(FName(*KV.Key));
				for (const TSharedPtr<FJsonValue>& V : KV.Value->AsArray())
				{
					const TSharedPtr<FJsonObject> O = V->AsObject();
					FMorphBoneOffset Off;
					Off.Bone = FName(*Str(O, TEXT("bone")));
					Off.bRotation = Str(O, TEXT("kind")) == TEXT("rot");
					if (Off.bRotation)
					{
						const TArray<TSharedPtr<FJsonValue>>* Q = nullptr;
						if (O->TryGetArrayField(TEXT("unreal_quat_xyzw"), Q) && Q->Num() == 4)
						{
							Off.Quat = FQuat((*Q)[0]->AsNumber(), (*Q)[1]->AsNumber(), (*Q)[2]->AsNumber(), (*Q)[3]->AsNumber()).GetNormalized();
						}
					}
					else
					{
						Off.Loc = ReadVec(O, TEXT("unreal_loc_cm"));
					}
					List.Add(Off);
				}
			}
		}
		const TSharedPtr<FJsonObject>* VO = nullptr;
		if (F->TryGetObjectField(TEXT("visemes"), VO))
		{
			for (const auto& KV : (*VO)->Values)
			{
				const TSharedPtr<FJsonObject> O = KV.Value->AsObject();
				const FName N(*KV.Key);
				VisemeNames.Add(N);
				VisemeNotes.Add(N, Str(O, TEXT("phonemes")));
				const TSharedPtr<FJsonObject>* W = nullptr;
				TMap<FName, float>& Map = Visemes.Add(N);
				if (O.IsValid() && O->TryGetObjectField(TEXT("controls"), W))
				{
					ReadWeights(*W, Map);
				}
			}
		}
		if (F->TryGetObjectField(TEXT("expressions"), VO))
		{
			for (const auto& KV : (*VO)->Values)
			{
				const FName N(*KV.Key);
				ExpressionNames.Add(N);
				ReadWeights(KV.Value->AsObject(), Expressions.Add(N));
			}
		}
		const TSharedPtr<FJsonObject>* EL = nullptr;
		if (F->TryGetObjectField(TEXT("eye_look"), EL))
		{
			EyeMaxYaw = (float)Num(*EL, TEXT("max_yaw_deg"), 32.0);
			EyeMaxPitchUp = (float)Num(*EL, TEXT("max_pitch_up_deg"), 22.0);
			EyeMaxPitchDown = (float)Num(*EL, TEXT("max_pitch_down_deg"), 28.0);
			LidUpperFollow = (float)Num(*EL, TEXT("lid_upper_follow"), 0.62);
			LidLowerFollow = (float)Num(*EL, TEXT("lid_lower_follow"), 0.32);
			Names.Reset();
			if ((*EL)->TryGetStringArrayField(TEXT("bones"), Names))
			{
				for (const FString& N : Names)
				{
					EyeBones.Add(FName(*N));
				}
			}
		}
	}
	// ------------------------------------------------------------------ dialogue alignment (optional)
	{
		FString Ignored;
		if (TSharedPtr<FJsonObject> D = LoadJson(TEXT("dialogue_alignment.json"), Ignored))
		{
			Dialogue.Text = Str(D, TEXT("text"));
			Dialogue.Duration = (float)Num(D, TEXT("duration"));
			const TSharedPtr<FJsonObject>* Cl = nullptr;
			if (D->TryGetObjectField(TEXT("clip"), Cl))
			{
				Dialogue.AudioStartTime = (float)Num(*Cl, TEXT("audio_start_time"));
			}
			auto ReadList = [&](const TCHAR* Field, const TCHAR* TextField, TArray<FMorphWord>& Out)
			{
				const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
				if (D->TryGetArrayField(Field, Arr))
				{
					for (const TSharedPtr<FJsonValue>& V : *Arr)
					{
						const TSharedPtr<FJsonObject> O = V->AsObject();
						FMorphWord W;
						W.Text = Str(O, TextField);
						W.Viseme = Str(O, TEXT("viseme"));
						W.Start = (float)Num(O, TEXT("start"));
						W.End = (float)Num(O, TEXT("end"));
						Out.Add(W);
					}
				}
			};
			ReadList(TEXT("words"), TEXT("word"), Dialogue.Words);
			ReadList(TEXT("phonemes"), TEXT("phoneme"), Dialogue.Phonemes);
		}
	}
	// ------------------------------------------------------------------ import report (optional): morph targets the import rejected
	{
		FString Ignored;
		if (TSharedPtr<FJsonObject> R = LoadJson(TEXT("import_report.json"), Ignored))
		{
			const TSharedPtr<FJsonObject>* MT = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
			if (R->TryGetObjectField(TEXT("morph_targets"), MT) && (*MT)->TryGetArrayField(TEXT("disabled"), Arr))
			{
				for (const TSharedPtr<FJsonValue>& V : *Arr)
				{
					DisabledMorphs.Add(FName(*V->AsString()));
				}
			}
		}
		if (DisabledMorphs.Num() > 0)
		{
			UE_LOG(LogMorphRig, Warning, TEXT("MorphRig data: %d morph targets failed the import sanity check and are not driven"), DisabledMorphs.Num());
		}
	}
	for (const FString& Missing : MissingControllerNames())
	{
		UE_LOG(LogMorphRig, Error, TEXT("MorphRig data: the controller needs '%s' but skeleton_and_sockets.json does not list it"), *Missing);
	}
	bValid = Clips.Num() > 0 && Bones.Num() > 0;
	if (!bValid)
	{
		UE_LOG(LogMorphRig, Error, TEXT("MorphRig data invalid: %s"), *Error);
	}
	else
	{
		UE_LOG(LogMorphRig, Display, TEXT("MorphRig data: %d clips, %d bones, %d helper rules, %d sockets, %d morphs, %d controls, %d visemes, %d expressions%s"),
			Clips.Num(), Bones.Num(), HelperRules.Num(), Sockets.Num(), Morphs.Num(), Controls.Num(), VisemeNames.Num(), ExpressionNames.Num(),
			bPlaceholder ? TEXT(" [PLACEHOLDER DATA]") : TEXT(""));
	}
}

TArray<FString> FMorphRigData::MissingControllerNames() const
{
	// everything else (helper rules, prop and cable bones, face bones, sockets for effects) is taken from the JSON by role
	static const TCHAR* NeededBones[] = { TEXT("root"), TEXT("pelvis"), TEXT("spine_01"), TEXT("spine_02"), TEXT("spine_03"), TEXT("neck_01"), TEXT("head"),
		TEXT("thigh_l"), TEXT("calf_l"), TEXT("foot_l"), TEXT("thigh_r"), TEXT("calf_r"), TEXT("foot_r"),
		TEXT("eye_l"), TEXT("eye_r"), TEXT("lid_upper_l"), TEXT("lid_upper_r"), TEXT("lid_lower_l"), TEXT("lid_lower_r"), TEXT("hand_l"), TEXT("hand_r") };
	static const TCHAR* NeededSockets[] = { TEXT("emitter_muzzle"), TEXT("hand_l_socket"), TEXT("hand_r_socket"), TEXT("blade_base"), TEXT("blade_tip") };
	TArray<FString> Out;
	for (const TCHAR* N : NeededBones)
	{
		if (!Bones.ContainsByPredicate([N](const FMorphBoneDef& B) { return B.Name == FName(N); }))
		{
			Out.Add(FString::Printf(TEXT("bone %s"), N));
		}
	}
	for (const TCHAR* N : NeededSockets)
	{
		if (!Sockets.ContainsByPredicate([N](const FMorphSocketDef& S) { return S.Name == FName(N); }))
		{
			Out.Add(FString::Printf(TEXT("socket %s"), N));
		}
	}
	return Out;
}
